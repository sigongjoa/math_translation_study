#!/usr/bin/env python3
"""
PDF Parser for The Princeton Companion to Mathematics
Extracts text and images by hierarchical sections with proper spacing
"""

import fitz  # PyMuPDF
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from tqdm import tqdm


class PDFParser:
    def __init__(self, pdf_path: str, output_dir: str = "output"):
        self.pdf_path = pdf_path
        self.output_dir = Path(output_dir)
        self.sections_dir = self.output_dir / "sections"
        self.images_dir = self.output_dir / "images"

        self.sections_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

        # PCM section patterns: "I.4", "2.2", "3.1.1", etc.
        self.part_pattern = re.compile(r'^Part\s+(I{1,3}V?|V?I{0,3})\b')
        self.section_pattern = re.compile(
            r'^(\d+(?:\.\d+)*)\s+([A-Z].+)$', re.MULTILINE
        )

        self.doc = None

    def __enter__(self):
        self.doc = fitz.open(self.pdf_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.doc:
            self.doc.close()

    def extract_text_from_page(self, page_num: int) -> str:
        """Extract text with proper spacing using PyMuPDF dict mode."""
        page = self.doc[page_num]
        blocks = page.get_text("dict")["blocks"]

        lines_out = []
        prev_block_bottom = 0

        for block in blocks:
            if block["type"] != 0:  # skip images
                continue

            block_top = block["bbox"][1]
            # Detect paragraph break (gap > 1.5x line height)
            if prev_block_bottom > 0 and (block_top - prev_block_bottom) > 12:
                lines_out.append("")  # empty line = paragraph break

            for line in block["lines"]:
                spans_text = []
                for span in line["spans"]:
                    text = span["text"]
                    if text.strip():
                        spans_text.append(text)
                if spans_text:
                    line_text = " ".join(spans_text)
                    # Clean up double spaces
                    line_text = re.sub(r'  +', ' ', line_text)
                    lines_out.append(line_text)

            prev_block_bottom = block["bbox"][3]

        return "\n".join(lines_out)

    def extract_text_with_fonts(self, page_num: int) -> List[Dict]:
        """Extract text with font info for detecting headers."""
        page = self.doc[page_num]
        blocks = page.get_text("dict")["blocks"]

        elements = []
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        elements.append({
                            "text": span["text"],
                            "font": span["font"],
                            "size": span["size"],
                            "bbox": span["bbox"],
                            "bold": "Bold" in span["font"] or "Demi" in span["font"],
                        })
        return elements

    def detect_sections_by_font(self, page_num: int) -> List[Tuple[str, str, float]]:
        """Detect section headers using font analysis (more reliable than regex)."""
        elements = self.extract_text_with_fonts(page_num)
        sections = []

        i = 0
        while i < len(elements):
            el = elements[i]
            # Section number: bold, size >= 8pt
            if el["bold"] and el["size"] >= 8.0:
                text = el["text"].strip()
                # Check if it's a section number like "2.2" or "3"
                if re.match(r'^\d+(?:\.\d+)*$', text):
                    sec_num = text
                    # Next element should be section title
                    if i + 1 < len(elements):
                        title_el = elements[i + 1]
                        if title_el["bold"] and abs(title_el["size"] - el["size"]) < 1:
                            title = title_el["text"].strip()
                            sections.append((sec_num, title, el["size"]))
                            i += 2
                            continue
            i += 1

        return sections

    def extract_images_from_page(self, page_num: int) -> List[Dict]:
        """Extract all images from a specific page."""
        images = []
        page = self.doc[page_num]
        image_list = page.get_images(full=True)

        for img_index, img in enumerate(image_list):
            xref = img[0]
            try:
                base_image = self.doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                img_rects = page.get_image_rects(xref)
                position = None
                if img_rects:
                    rect = img_rects[0]
                    position = {
                        "x": rect.x0, "y": rect.y0,
                        "width": rect.width, "height": rect.height
                    }

                image_filename = f"page_{page_num + 1}_img_{img_index}.{image_ext}"
                image_path = self.images_dir / image_filename

                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)

                images.append({
                    "filename": image_filename,
                    "position": position,
                    "page": page_num + 1,
                    "path": str(image_path)
                })
            except Exception as e:
                print(f"  Warning: Could not extract image on page {page_num+1}: {e}")

        return images

    def parse_full_document(self, start_page: int = 0, end_page: Optional[int] = None) -> Dict:
        """Parse the document and extract sections with proper text."""
        if end_page is None:
            end_page = len(self.doc)

        all_sections = {}
        current_section = None
        current_content = []
        current_images = []
        page_range_start = start_page

        for page_num in tqdm(range(start_page, min(end_page, len(self.doc))),
                             desc="Parsing PDF", unit="page"):

            text = self.extract_text_from_page(page_num)
            images = self.extract_images_from_page(page_num)

            # Detect sections using font analysis
            sections = self.detect_sections_by_font(page_num)

            if sections:
                # Save previous section
                if current_section:
                    all_sections[current_section["section_id"]] = {
                        **current_section,
                        "content_original": "\n".join(current_content),
                        "images": current_images,
                        "page_range": [page_range_start + 1, page_num]
                    }

                sec_num, sec_title, font_size = sections[0]
                # Determine hierarchy from font size
                level = "section" if font_size >= 9.0 else "subsection"

                current_section = {
                    "section_id": sec_num,
                    "title_original": sec_title,
                    "title_translated": "",
                    "level": level,
                    "font_size": font_size,
                }
                current_content = [text]
                current_images = images.copy()
                page_range_start = page_num
            else:
                if text.strip():
                    current_content.append(text)
                current_images.extend(images)

        # Save last section
        if current_section:
            all_sections[current_section["section_id"]] = {
                **current_section,
                "content_original": "\n".join(current_content),
                "images": current_images,
                "page_range": [page_range_start + 1, end_page]
            }

        return all_sections

    def save_sections_to_json(self, sections: Dict):
        """Save each section to a separate JSON file."""
        for section_id, section_data in sections.items():
            safe_filename = section_id.replace(".", "_") + ".json"
            output_path = self.sections_dir / safe_filename

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(section_data, f, ensure_ascii=False, indent=2)

            print(f"Saved section {section_id} to {output_path}")

    def save_metadata(self, sections: Dict):
        """Save overall metadata."""
        metadata = {
            "total_sections": len(sections),
            "section_ids": list(sections.keys()),
            "pdf_path": self.pdf_path,
            "total_pages": len(self.doc)
        }

        metadata_path = self.output_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        print(f"Saved metadata to {metadata_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Parse PDF and extract sections")
    parser.add_argument("--input", default="PCM.pdf", help="Input PDF file")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--start-page", type=int, default=0, help="Start page (0-indexed)")
    parser.add_argument("--end-page", type=int, default=None, help="End page (0-indexed)")
    parser.add_argument("--test", action="store_true", help="Test mode: process first 5 pages")

    args = parser.parse_args()

    if args.test:
        args.end_page = 5
        print("TEST MODE: Processing first 5 pages only")

    print(f"Parsing PDF: {args.input}")
    print(f"Output directory: {args.output}")

    with PDFParser(args.input, args.output) as p:
        sections = p.parse_full_document(args.start_page, args.end_page)
        print(f"\nFound {len(sections)} sections")

        p.save_sections_to_json(sections)
        p.save_metadata(sections)

    print("\nParsing complete!")


if __name__ == "__main__":
    main()
