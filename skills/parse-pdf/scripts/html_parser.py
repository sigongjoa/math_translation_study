#!/usr/bin/env python3
"""
html_parser.py — Extract structured sections + figures from a book HTML page.

Parses `div.section > div.para + div.figure` structure (Feynman-style),
downloads images with Playwright (Cloudflare-bypass), converts SVGZ→PNG.

Usage:
  python html_parser.py /path/to/page.html \
    --base-url https://www.feynmanlectures.caltech.edu \
    --output workspace/sections.json \
    --images-dir workspace/images
"""

import argparse
import gzip
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 not installed. Run: pip install beautifulsoup4", file=sys.stderr)
    sys.exit(1)

try:
    import cairosvg
    HAS_CAIROSVG = True
except ImportError:
    HAS_CAIROSVG = False
    print("WARNING: cairosvg not installed. SVG images saved as SVG.", file=sys.stderr)


NOISE_PATTERNS = [
    r'LOADING PAGE', r'Dear Reader', r'sending us information',
    r'does not open', r'MathJax', r'Copyright ©',
]

THEOREM_PATTERNS = [
    (r'^(Theorem|Théorème)\s+[\d\.]+[\.:]?\s', "theorem"),
    (r'^(Lemma|Lemme)\s+[\d\.]+[\.:]?\s', "lemma"),
    (r'^(Corollary|Corollaire)\s+[\d\.]+[\.:]?\s', "corollary"),
    (r'^(Proposition)\s+[\d\.]+[\.:]?\s', "theorem"),
    (r'^(Definition|Définition)\s+[\d\.]+[\.:]?\s', "definition"),
    (r'^(Example|Exemple)\s+[\d\.]*[\.:]?\s?', "example"),
    (r'^(Remark|Remarque|Note)\s*[\d\.]*[\.:]?\s?', "remark"),
    (r'^Proof[\.\s]', "proof"),
]


def _is_noise(text):
    return any(re.search(p, text, re.IGNORECASE) for p in NOISE_PATTERNS)


def _detect_type(text):
    for pattern, btype in THEOREM_PATTERNS:
        if re.match(pattern, text, re.IGNORECASE):
            m = re.match(r'^(\w+\s+[\d\.]*)', text, re.IGNORECASE)
            return btype, (m.group(1).strip() if m else "")
    return "text", ""


def _clean(text):
    return re.sub(r'\s+', ' ', text).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Image download with Playwright (Cloudflare-aware)
# ─────────────────────────────────────────────────────────────────────────────

def bulk_download_images_via_playwright(img_urls: list[str], images_dir: Path, page_url: str) -> dict[str, str]:
    """
    Load the source page in Playwright and intercept all image responses.
    Returns {src_url: local_path} for successfully captured images.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {}

    captured = {}  # url → bytes

    def handle_response(response):
        url = response.url
        if any(url == img_url for img_url in img_urls):
            try:
                body = response.body()
                if body:
                    captured[url] = body
            except Exception:
                pass

    print(f"  Loading page to intercept images: {page_url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            pg = ctx.new_page()
            pg.on("response", handle_response)
            pg.goto(page_url, timeout=60000, wait_until="load")
            browser.close()
    except Exception as e:
        print(f"  WARNING: Page load failed: {e}", file=sys.stderr)

    # Save captured images
    result = {}
    for url, data in captured.items():
        filename = Path(urlparse(url).path).name
        stem = Path(filename).stem
        path = _save_image(data, filename, images_dir)
        if path:
            result[url] = path
            print(f"  Captured: {filename} → OK")
    return result


def _download_with_requests(url: str, referer: str = "") -> bytes | None:
    """Fetch binary content with browser-like headers (handles hotlink protection)."""
    try:
        import requests
    except ImportError:
        return None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer or url,
        "Connection": "keep-alive",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.ok:
            return resp.content
    except Exception:
        pass
    return None


def _download_with_playwright(url: str, referer: str = "") -> bytes | None:
    """
    Fetch binary content using a real browser context.
    Navigates to the referer page first to establish cookies/session,
    then fetches the image URL using the browser's API request context.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            # Warm up session by visiting referer page
            if referer and referer != url:
                pg = ctx.new_page()
                try:
                    pg.goto(referer, timeout=20000, wait_until="load")
                except Exception:
                    pass
                pg.close()

            # Fetch the image using the browser's API request (same cookies/session)
            api_req = ctx.request
            resp = api_req.get(url, headers={"Referer": referer or url})
            data = resp.body() if resp.ok else None
            browser.close()
            return data
    except Exception as e:
        print(f"  WARNING: Playwright fetch failed for {url}: {e}", file=sys.stderr)
        return None


def _save_image(content: bytes, filename: str, images_dir: Path) -> str | None:
    """Decompress SVGZ, convert SVG→PNG, save. Returns relative path."""
    stem = Path(filename).stem
    suffix = Path(filename).suffix.lower()

    if suffix == ".svgz":
        try:
            content = gzip.decompress(content)
        except Exception:
            pass
        suffix = ".svg"

    if suffix == ".svg":
        if HAS_CAIROSVG:
            out_name = stem + ".png"
            try:
                png = cairosvg.svg2png(bytestring=content, scale=2.0)
                (images_dir / out_name).write_bytes(png)
                return f"workspace/images/{out_name}"
            except Exception as e:
                print(f"  WARNING: SVG→PNG failed for {filename}: {e}", file=sys.stderr)
        out_name = stem + ".svg"
        (images_dir / out_name).write_bytes(content)
        return f"workspace/images/{out_name}"

    out_name = stem + suffix
    (images_dir / out_name).write_bytes(content)
    return f"workspace/images/{out_name}"


def download_image(src_url: str, images_dir: Path, page_url: str = "") -> str | None:
    """Download and convert an image. Returns workspace-relative path."""
    filename = Path(urlparse(src_url).path).name
    if not filename:
        return None

    # Check cache
    stem = Path(filename).stem
    cached_png = images_dir / (stem + ".png")
    if cached_png.exists():
        return f"workspace/images/{stem}.png"

    print(f"  Downloading: {filename} ...", end=" ", flush=True)

    # Try requests with Referer first (faster)
    data = _download_with_requests(src_url, referer=page_url or src_url)

    # Fallback: Playwright with session warm-up
    if not data:
        data = _download_with_playwright(src_url, referer=page_url or src_url)

    if not data:
        print("FAILED")
        return None

    path = _save_image(data, filename, images_dir)
    print("OK" if path else "SAVE ERROR")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# HTML parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_figure_div(div, base_url: str, images_dir: Path, page_url: str = "", img_cache: dict = None) -> dict | None:
    """Parse a div.figure → download image → return figure dict."""
    img_tag = div.find("img")
    if not img_tag:
        return None

    src = img_tag.get("src", "")
    if not src:
        return None

    img_url = src if src.startswith("http") else urljoin(base_url + "/", src)
    cap_div = div.find("div", class_="caption") or div.find("figcaption")
    caption = _clean(cap_div.get_text()) if cap_div else _clean(div.get_text())

    # Check bulk-download cache first
    if img_cache and img_url in img_cache:
        local_path = img_cache[img_url]
    else:
        local_path = download_image(img_url, images_dir, page_url=page_url)

    return {
        "id": div.get("id", ""),
        "src_url": img_url,
        "file": local_path,
        "caption": caption,
        "caption_ko": "",  # filled by /translate-section
    }


def _para_text(div) -> str:
    """Get text from a div.para, preserving math markers."""
    return _clean(div.get_text())


def extract_sections_and_figures(
    html_path: str,
    base_url: str,
    images_dir: Path,
    page_url: str = "",
) -> list[dict]:
    """
    Parse a Feynman-style HTML page.

    Structure expected:
      div.section > h3.section-title, div.para, div.figure (interleaved)

    Falls back to a generic paragraph scan if no div.section found.
    """
    with open(html_path, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Pre-collect all image URLs from figure divs
    all_img_urls = []
    for div in soup.find_all("div", class_="figure"):
        img = div.find("img")
        if img and img.get("src"):
            src = img["src"]
            url = src if src.startswith("http") else urljoin(base_url + "/", src)
            all_img_urls.append(url)

    # Bulk-download all images via page interception (avoids per-request Cloudflare)
    img_cache = {}  # src_url → local_path
    if all_img_urls and page_url:
        img_cache = bulk_download_images_via_playwright(all_img_urls, images_dir, page_url)

    sections = []
    counter = [0]

    def new_section(page, btype, label, content, figures=None) -> dict:
        counter[0] += 1
        return {
            "id": f"p{page:03d}_s{counter[0]:03d}",
            "page": page,
            "type": btype,
            "label": label,
            "content": content,
            **({"figures": figures} if figures else {}),
        }

    # ── Try Feynman-style structure first ──────────────────────────────────
    section_divs = soup.find_all("div", class_="section")
    if section_divs:
        page_num = 1
        for sec_div in section_divs:
            # Section heading
            h = sec_div.find(["h2", "h3", "h4"], class_=lambda c: c and "title" in c)
            if h:
                title_text = _clean(h.get_text())
                if title_text and not _is_noise(title_text):
                    sections.append(new_section(page_num, "subsection", "", title_text))

            # Process children: each div.para → its own section; div.figure → attaches to previous
            children = [c for c in sec_div.children if hasattr(c, 'name') and c.name]
            for child in children:
                cls = child.get("class", [])
                tag = child.name

                if tag in ("h2", "h3", "h4") and "title" in " ".join(cls):
                    continue  # already handled above

                if "figure" in cls:
                    fig = _parse_figure_div(child, base_url, images_dir, page_url=page_url, img_cache=img_cache)
                    if fig:
                        # Attach to most recent section
                        if sections:
                            sections[-1].setdefault("figures", []).append(fig)

                elif "para" in cls or tag == "p":
                    text = _para_text(child)
                    if text and not _is_noise(text) and len(text) > 15:
                        btype, label = _detect_type(text)
                        sections.append(new_section(page_num, btype, label, text))

                elif tag == "div":
                    # Generic div — might contain paragraphs
                    text = _para_text(child)
                    if text and not _is_noise(text) and len(text) > 30:
                        btype, label = _detect_type(text)
                        sections.append(new_section(page_num, btype, label, text))

        return sections

    # ── Generic fallback: scan all paragraphs and figure divs ──────────────
    print("  (no div.section found, using generic paragraph scan)", file=sys.stderr)
    page_num = 1
    body = soup.find("body") or soup

    for tag in body.find_all(["h1", "h2", "h3", "h4", "p", "div"]):
        cls = tag.get("class", [])

        if tag.name in ("h1", "h2", "h3", "h4"):
            text = _clean(tag.get_text())
            if text and not _is_noise(text):
                btype = "section" if tag.name in ("h1", "h2") else "subsection"
                sections.append(new_section(page_num, btype, "", text))

        elif tag.name == "p":
            text = _clean(tag.get_text())
            if text and not _is_noise(text) and len(text) > 20:
                if sections and sections[-1]["type"] == "text":
                    sections[-1]["content"] += " " + text
                else:
                    btype, label = _detect_type(text)
                    sections.append(new_section(page_num, btype, label, text))

        elif tag.name == "div" and "figure" in cls:
            fig = _parse_figure_div(tag, base_url, images_dir)
            if fig and sections:
                sections[-1].setdefault("figures", []).append(fig)

    return sections


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract sections + figures from a book HTML page"
    )
    parser.add_argument("html_path", help="Path to saved HTML file")
    parser.add_argument(
        "--base-url", required=True,
        help="Base URL for image resolution (e.g. https://www.feynmanlectures.caltech.edu)"
    )
    parser.add_argument("--output", default="workspace/sections.json")
    parser.add_argument("--images-dir", default="workspace/images")
    parser.add_argument(
        "--page-url", default="",
        help="Full URL of the page being parsed (used as Referer for image downloads). "
             "Defaults to --base-url."
    )
    args = parser.parse_args()

    html_path = Path(args.html_path)
    if not html_path.exists():
        print(f"ERROR: File not found: {html_path}", file=sys.stderr)
        sys.exit(1)

    images_dir = Path(args.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"Parsing {html_path.name} ...")
    print(f"Base URL : {args.base_url}")
    print(f"Images → {images_dir}/")

    page_url = args.page_url or args.base_url
    sections = extract_sections_and_figures(str(html_path), args.base_url, images_dir, page_url=page_url)

    type_counts = {}
    fig_count = 0
    for s in sections:
        type_counts[s["type"]] = type_counts.get(s["type"], 0) + 1
        fig_count += len(s.get("figures", []))

    output = {
        "source_html": str(html_path),
        "base_url": args.base_url,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "sections": sections,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nExtracted {len(sections)} sections, {fig_count} figures → {out_path}")
    print("\nBreakdown:")
    for btype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {btype:12s}: {count}")

    imgs = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.svg"))
    if imgs:
        print(f"\nImages: {len(imgs)} files in {images_dir}/")


if __name__ == "__main__":
    main()
