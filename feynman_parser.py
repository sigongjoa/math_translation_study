import os
import json
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin

# Backend Persona: Implementing a clean parser for structured data extraction
# Goal: Convert Caltech Feynman HTML to structured JSON for translation pipeline

class FeynmanParser:
    def __init__(self, raw_dir="feynman_raw", output_dir="feynman_json"):
        self.raw_dir = raw_dir
        self.output_dir = output_dir
        self.img_dir = os.path.join(output_dir, "images")
        
        for d in [self.output_dir, self.img_dir]:
            if not os.path.exists(d):
                os.makedirs(d)

    def parse_file(self, filename):
        filepath = os.path.join(self.raw_dir, filename)
        if not os.path.exists(filepath):
            print(f"[ERR] File not found: {filepath}")
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        # Find the main chapter container
        chapter_div = soup.find("div", class_="chapter") or soup.find("div", class_="document")
        if not chapter_div:
            print(f"[ERR] Could not find chapter container in {filename}")
            return None

        chapter_id = chapter_div.get("id", "Unknown")
        title_tag = chapter_div.find("h2", class_="chapter-title")
        
        # Clean title: Remove tags and footnotes
        if title_tag:
            # Clone and remove tags/sup
            title_copy = BeautifulSoup(str(title_tag), "html.parser").find("h2")
            for tag in title_copy.find_all(["span", "sup", "a"]):
                tag.decompose()
            chapter_title = title_copy.get_text(strip=True)
        else:
            chapter_title = "Untitled"

        data = {
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            "sections": []
        }

        current_section = {
            "title": "Introduction",
            "content": []
        }

        # Iterate through elements in the chapter
        for element in chapter_div.find_all(recursive=False):
            if element.name == "div" and "section" in element.get("class", []):
                if current_section["content"]:
                    data["sections"].append(current_section)
                
                # Start new section
                section_title_tag = element.find("h3")
                if section_title_tag:
                    # Clean section title
                    title_copy = BeautifulSoup(str(section_title_tag), "html.parser").find("h3")
                    for tag in title_copy.find_all(["span", "sup", "a"]):
                        tag.decompose()
                    section_title = title_copy.get_text(strip=True)
                else:
                    section_title = "Untitled Section"
                
                current_section = {
                    "title": section_title,
                    "content": []
                }
                self._parse_section_content(element, current_section)
            
            elif element.name == "div" and "para" in element.get("class", []):
                self._parse_para(element, current_section)
            
            elif element.name == "div" and "figure" in element.get("class", []):
                self._parse_figure(element, current_section)
            elif element.name == "div" and "equation" in element.get("class", []):
                self._parse_equation(element, current_section)

        if current_section["content"]:
            data["sections"].append(current_section)

        # Save to JSON
        json_filename = filename.replace(".html", ".json")
        json_path = os.path.join(self.output_dir, json_filename)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[OK] Parsed {filename} to {json_path}")
        return data

    def _parse_section_content(self, section_div, section_obj):
        # We need to preserve order, so we iterate through all children
        for element in section_div.find_all(recursive=False):
            if element.name == "div" and "para" in element.get("class", []):
                self._parse_para(element, section_obj)
            elif element.name == "div" and "figure" in element.get("class", []):
                self._parse_figure(element, section_obj)
            elif element.name == "div" and "equation" in element.get("class", []):
                self._parse_equation(element, section_obj)

    def _extract_text_with_math(self, element):
        """Extract text while preserving LaTeX math from MathJax script tags."""
        parts = []
        for child in element.children:
            if hasattr(child, "name") and child.name == "script" and child.get("type") == "math/tex":
                # Inline MathJax: <script type="math/tex">...</script>
                latex = (child.string or "").strip()
                parts.append(f"${latex}$")
            elif hasattr(child, "name") and child.name == "script" and child.get("type") == "math/tex; mode=display":
                # Display MathJax
                latex = (child.string or "").strip()
                parts.append(f"$${latex}$$")
            elif hasattr(child, "name") and child.name == "span" and "MathJax" in " ".join(child.get("class", [])):
                # Rendered MathJax span — skip (the script tag has the source)
                continue
            elif hasattr(child, "name") and child.name:
                # Recurse into other tags
                parts.append(self._extract_text_with_math(child))
            else:
                # Plain text node
                text = " ".join(str(child).split()).strip() # Normalize whitespace
                if text:
                    parts.append(text)
        return " ".join(parts).strip()

    def _parse_para(self, para_div, section_obj):
        p_tag = para_div.find("p", class_="p")
        if not p_tag:
            return
        # Extract text while preserving MathJax LaTeX
        text = self._extract_text_with_math(p_tag)
        if text.strip():
            section_obj["content"].append({
                "type": "paragraph",
                "text": text
            })

    def _parse_figure(self, fig_div, section_obj):
        img = fig_div.find("img")
        caption = fig_div.find("div", class_="caption")
        if img:
            # Caltech site uses data-src for late loading
            src = img.get("src") or img.get("data-src")
            if not src:
                print(f"[WARN] Found img tag without src or data-src in {fig_div.get('id', 'unknown')}")
                return

            # Handle relative paths for downloading
            base_img_url = "https://www.feynmanlectures.caltech.edu/"
            full_img_url = urljoin(base_img_url, src)
            
            # Local filename
            img_filename = os.path.basename(src)
            local_img_path = os.path.join(self.img_dir, img_filename)
            
            # Download if not exists
            if not os.path.exists(local_img_path):
                try:
                    # Backend Persona: Use stealth headers to bypass 403 on assets
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                        "Referer": "https://www.feynmanlectures.caltech.edu/",
                        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
                    }
                    r = requests.get(full_img_url, headers=headers, timeout=15)
                    if r.status_code == 200:
                        with open(local_img_path, "wb") as f:
                            f.write(r.content)
                        print(f"[OK] Downloaded: {img_filename}")
                    else:
                        print(f"[WARN] Failed to download image {full_img_url}: {r.status_code}")
                except Exception as e:
                    print(f"[WARN] Error downloading image {full_img_url}: {e}")

            cap_text = caption.get_text(strip=True) if caption else ""
            section_obj["content"].append({
                "type": "figure",
                "src": f"images/{img_filename}",
                "caption": cap_text
            })

    def _parse_equation(self, eq_div, section_obj):
        """Extract equation LaTeX from MathJax script tags."""
        script = eq_div.find("script", type=lambda t: t and "math/tex" in t)
        if script and script.string:
            section_obj["content"].append({
                "type": "equation",
                "latex": script.string.strip()
            })
        else:
            eq_text = eq_div.get_text(strip=True)
            if eq_text:
                section_obj["content"].append({
                    "type": "equation",
                    "latex": eq_text
                })

if __name__ == "__main__":
    parser = FeynmanParser()
    parser.parse_file("I_01.html")
