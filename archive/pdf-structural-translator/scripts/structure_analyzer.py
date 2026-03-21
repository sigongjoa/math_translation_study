import fitz
import re
import json
from pathlib import Path

class PDFStructureAnalyzer:
    """
    Analyzes PDF font/style patterns to extract logical structures 
    (Definition, Example, Exercise, Remark) instead of raw text.
    """
    
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        # Patterns based on 'Seven Sketches' analysis
        self.structural_keywords = ['Definition', 'Example', 'Exercise', 'Remark', 'Proposition', 'Theorem']
        self.end_marker_text = '♦'
        self.end_marker_font = 'txsya'

    def extract_blocks(self, start_page, end_page):
        """Extracts structured blocks from a page range."""
        blocks = []
        current_block = None

        for page_num in range(start_page, end_page):
            page = self.doc[page_num]
            page_dict = page.get_text("dict")
            
            for b in page_dict["blocks"]:
                if "lines" not in b:
                    continue
                
                for l in b["lines"]:
                    for s in l["spans"]:
                        text = s["text"].strip()
                        font = s["font"]
                        
                        if not text:
                            continue

                        # Detect Start of a Structural Block
                        # Pattern: Italic/Bold font + Keyword at start
                        is_structural_start = any(text.startswith(kw) for kw in self.structural_keywords) and 
                                             ("Italic" in font or "Bold" in font)

                        if is_structural_start:
                            # Flush previous block if any
                            if current_block:
                                blocks.append(current_block)
                            
                            # Start new block
                            kw = next(kw for kw in self.structural_keywords if text.startswith(kw))
                            current_block = {
                                "type": kw.lower(),
                                "label": text,
                                "content": "",
                                "page_start": page_num,
                                "font": font
                            }
                            continue

                        # Detect End Marker (♦)
                        if self.end_marker_text in text and self.end_marker_font in font:
                            if current_block:
                                current_block["content"] += " " + text
                                current_block["page_end"] = page_num
                                blocks.append(current_block)
                                current_block = None
                            continue

                        # Accumulate content
                        if current_block:
                            current_block["content"] += " " + text
                        else:
                            # Ordinary text block
                            if not blocks or blocks[-1]["type"] != "text":
                                blocks.append({
                                    "type": "text",
                                    "content": text,
                                    "page_start": page_num
                                })
                            else:
                                blocks[-1]["content"] += " " + text

        if current_block:
            blocks.append(current_block)
            
        return self.clean_blocks(blocks)

    def clean_blocks(self, blocks):
        """Cleanup whitespace and normalize content."""
        for b in blocks:
            b["content"] = re.sub(r'\s+', ' ', b["content"]).strip()
        return blocks

if __name__ == "__main__":
    # Quick test
    analyzer = PDFStructureAnalyzer("/mnt/d/progress/the princeton companion to mathematics/asset/Seven Sketches in Compositionality AnInvitation to Applied Category Theory.pdf")
    test_blocks = analyzer.extract_blocks(21, 23)
    print(json.dumps(test_blocks[:3], indent=2, ensure_ascii=False))
