#!/usr/bin/env python3
"""
pdf_parser.py — Extract structured sections from a PDF for translation.

Detects block types: section, subsection, definition, theorem, lemma,
corollary, proof, example, remark, text.

Output: sections.json
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install pymupdf", file=sys.stderr)
    sys.exit(1)


# Colors used in PCM-style books for shaded boxes (RGB 0-1)
SHADED_BOX_COLORS = {
    "definition": (0.98, 0.92, 0.94),
    "example":    (0.93, 1.00, 0.93),
    "remark":     (0.92, 0.92, 1.00),
}

# Patterns to detect theorem-like blocks by text prefix
THEOREM_PATTERNS = [
    (r'^(Theorem|Théorème)\s+[\d\.]+[\.:]?\s', "theorem"),
    (r'^(Lemma|Lemme)\s+[\d\.]+[\.:]?\s', "lemma"),
    (r'^(Corollary|Corollaire)\s+[\d\.]+[\.:]?\s', "corollary"),
    (r'^(Proposition)\s+[\d\.]+[\.:]?\s', "theorem"),
    (r'^(Definition|Définition)\s+[\d\.]+[\.:]?\s', "definition"),
    (r'^(Example|Exemple)\s+[\d\.]*[\.:]?\s?', "example"),
    (r'^(Remark|Remarque|Note)\s*[\d\.]*[\.:]?\s?', "remark"),
    (r'^Proof[\.\s]', "proof"),
    (r'^Proof of\s', "proof"),
]


def _color_distance(c1, c2):
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


def _match_shaded_color(color):
    if color is None:
        return None
    rounded = tuple(round(c, 2) for c in color)
    for btype, ref_color in SHADED_BOX_COLORS.items():
        if _color_distance(rounded, ref_color) < 0.05:
            return btype
    return None


def _detect_type_from_text(text):
    """Detect block type from text prefix patterns."""
    for pattern, btype in THEOREM_PATTERNS:
        if re.match(pattern, text, re.IGNORECASE):
            label_match = re.match(r'^(\w+\s+[\d\.]*)', text, re.IGNORECASE)
            label = label_match.group(1).strip() if label_match else ""
            return btype, label
    return None, None


def _is_section_heading(text, is_bold, font_size):
    """Detect numbered section headings."""
    # "1.2 Some Title" or "1 Introduction"
    if is_bold and font_size > 12 and re.match(r'^\d+[\.\d]*\s+\w', text):
        return True
    # Common unnumbered headings
    if is_bold and font_size > 11 and re.match(
        r'^(Abstract|Introduction|Background|Related Work|Conclusion|'
        r'Discussion|Method(?:ology)?|Experiment|Results?|References?|'
        r'Appendix|Acknowledgements?|Preliminaries|Notation|Overview)\b',
        text, re.IGNORECASE
    ):
        return True
    return False


def _is_subsection_heading(text, is_bold, font_size):
    """Detect numbered subsection headings."""
    if is_bold and font_size > 10 and re.match(r'^\d+\.\d+\.\d+\s+\w', text):
        return True
    return False


def extract_images_from_page(page, page_num: int, doc, images_dir: Path) -> list:
    """Extract embedded images from a PDF page. Returns list of figure dicts."""
    figures = []
    image_list = page.get_images(full=True)
    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]
        try:
            base_image = doc.extract_image(xref)
        except Exception:
            continue
        img_bytes = base_image["image"]
        img_ext = base_image["ext"]  # "png", "jpeg", etc.
        w, h = base_image["width"], base_image["height"]
        # Skip tiny images (icons, decorations)
        if w < 50 or h < 50:
            continue
        fname = f"p{page_num+1:03d}_img_{img_idx}.{img_ext}"
        out_path = images_dir / fname
        out_path.write_bytes(img_bytes)
        figures.append({
            "id": f"fig-p{page_num+1}-{img_idx}",
            "file": f"workspace/images/{fname}",
            "caption": "",
            "caption_ko": "",
        })
    return figures


def extract_sections(pdf_path, start_page, end_page, images_dir: Path = None):
    """Extract structured sections from pages [start_page, end_page)."""
    doc = fitz.open(pdf_path)
    all_sections = []
    section_counter = {}  # page -> count

    if images_dir is not None:
        images_dir.mkdir(parents=True, exist_ok=True)

    for page_num in range(start_page, min(end_page, len(doc))):
        page = doc[page_num]
        page_label = f"p{page_num + 1:03d}"
        section_counter[page_num] = 0

        # --- Detect shaded boxes ---
        drawings = page.get_drawings()
        shaded_rects = []
        for d in drawings:
            fill = d.get("fill")
            btype = _match_shaded_color(fill)
            if btype:
                shaded_rects.append({"rect": d["rect"], "btype": btype})
        shaded_rects.sort(key=lambda r: r["rect"].y0)

        def get_box_type(rect):
            for s in shaded_rects:
                if fitz.Rect(rect).intersects(s["rect"]):
                    return s["btype"], s["rect"]
            return None, None

        # --- Extract text blocks ---
        blocks = page.get_text("dict")["blocks"]
        pending = []  # accumulated (type, label, content, box_rect)

        def flush_pending():
            if pending:
                sec = pending.copy()
                pending.clear()
                return sec
            return []

        for b in sorted(blocks, key=lambda x: x["bbox"][1]):
            if "lines" not in b:
                continue

            bbox = b["bbox"]
            # Filter headers/footers (typically within 50px of top/bottom)
            page_height = page.rect.height
            if bbox[1] < 50 or bbox[3] > page_height - 50:
                continue

            block_text = ""
            is_bold = False
            max_size = 0.0
            for line in b["lines"]:
                for span in line["spans"]:
                    block_text += span["text"] + " "
                    if "Bold" in span.get("font", ""):
                        is_bold = True
                    max_size = max(max_size, span.get("size", 0))

            block_text = re.sub(r'\s+', ' ', block_text).strip()
            if not block_text:
                continue

            btype_shaded, box_rect = get_box_type(bbox)

            # --- Determine block type ---
            if _is_subsection_heading(block_text, is_bold, max_size):
                btype = "subsection"
                label = ""
            elif _is_section_heading(block_text, is_bold, max_size):
                btype = "section"
                label = ""
            elif btype_shaded:
                # Color-coded box (definition/example/remark)
                btype = btype_shaded
                label_match = re.match(r'^([A-Za-z]+\s+[\d\.]+)[\.:]?\s*', block_text)
                label = label_match.group(1) if label_match else ""
                # Merge blocks within the same shaded box
                if all_sections and all_sections[-1].get("_box_rect") == str(box_rect):
                    all_sections[-1]["content"] += " " + block_text
                    continue
            else:
                # Try text-pattern detection (Theorem 1.1, Proof, etc.)
                det_type, det_label = _detect_type_from_text(block_text)
                if det_type:
                    btype = det_type
                    label = det_label
                else:
                    btype = "text"
                    label = ""
                    # Merge consecutive text blocks
                    if all_sections and all_sections[-1]["type"] == "text" \
                            and all_sections[-1]["page"] == page_num + 1:
                        all_sections[-1]["content"] += " " + block_text
                        continue

            section_counter[page_num] += 1
            sec_id = f"{page_label}_s{section_counter[page_num]:03d}"

            entry = {
                "id": sec_id,
                "page": page_num + 1,
                "type": btype,
                "label": label,
                "content": block_text,
            }
            if btype_shaded:
                entry["_box_rect"] = str(box_rect)

            all_sections.append(entry)

        # Attach page images to the last section on this page
        if images_dir is not None:
            page_figures = extract_images_from_page(page, page_num, doc, images_dir)
            if page_figures:
                # Find last section on this page
                page_sections = [s for s in all_sections if s["page"] == page_num + 1]
                if page_sections:
                    last_sec = page_sections[-1]
                    last_sec.setdefault("figures", []).extend(page_figures)

    # Remove internal _box_rect keys
    for s in all_sections:
        s.pop("_box_rect", None)

    doc.close()
    return all_sections


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured sections from a PDF for translation"
    )
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument(
        "--pages", default=None,
        help="Page range to extract, e.g. '1-50' (1-indexed, inclusive). "
             "Default: first 20 pages."
    )
    parser.add_argument(
        "--output", default="workspace/sections.json",
        help="Output JSON file path (default: workspace/sections.json)"
    )
    parser.add_argument(
        "--images-dir", default=None,
        help="Directory to extract embedded images (e.g. workspace/images). "
             "Omit to skip image extraction."
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"ERROR: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Parse page range (1-indexed, convert to 0-indexed)
    if args.pages:
        parts = args.pages.split("-")
        if len(parts) == 2:
            start_page = int(parts[0]) - 1
            end_page = int(parts[1])
        else:
            start_page = int(parts[0]) - 1
            end_page = int(parts[0])
        pages_str = args.pages
    else:
        start_page = 0
        end_page = 20
        pages_str = f"1-{end_page}"

    images_dir = Path(args.images_dir) if args.images_dir else None
    print(f"Parsing {pdf_path.name} pages {pages_str}...")
    if images_dir:
        print(f"Extracting images → {images_dir}/")

    sections = extract_sections(str(pdf_path), start_page, end_page, images_dir=images_dir)

    # Count by type
    type_counts = {}
    for s in sections:
        type_counts[s["type"]] = type_counts.get(s["type"], 0) + 1

    output = {
        "source_pdf": str(pdf_path),
        "pages": pages_str,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "sections": sections,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nExtracted {len(sections)} sections → {out_path}")
    print("\nBreakdown:")
    for btype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {btype:12s}: {count}")

    if sections:
        print("\nFirst 3 sections:")
        for s in sections[:3]:
            preview = s["content"][:80].replace("\n", " ")
            label = f" [{s['label']}]" if s["label"] else ""
            print(f"  [{s['id']}] {s['type']}{label}: {preview}...")


if __name__ == "__main__":
    main()
