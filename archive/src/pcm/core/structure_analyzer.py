import fitz
import re
from pathlib import Path

class PDFStructureAnalyzer:
    """
    Analyzes PDF to extract the ORIGINAL book structure (Chapter, Section, Subsection)
    while preserving the text flow and shaded boxes.
    """
    
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        
        # Original colors for shaded boxes
        self.COLORS = {
            "definition": (0.98, 0.92, 0.94),
            "example": (0.93, 1.0, 0.93),
            "remark": (0.92, 0.92, 1.0)
        }

    def extract_structure(self, start_page, end_page):
        """Extracts text and boxes while filtering out page headers/footers."""
        all_elements = []
        
        for page_num in range(start_page, end_page):
            page = self.doc[page_num]
            
            # 1. Identify shaded boxes on this page
            drawings = page.get_drawings()
            shaded_rects = []
            for d in drawings:
                fill = d.get("fill")
                if fill:
                    rounded = tuple(round(c, 2) for c in fill)
                    shaded_rects.append({"rect": d["rect"], "color": rounded})
            shaded_rects.sort(key=lambda r: r["rect"].y0)

            # 2. Extract text blocks, filtering headers/footers (y < 50 or y > 750)
            # and identifying section headers
            blocks = page.get_text("dict")["blocks"]
            
            # Helper to check if a point is inside any shaded box
            def get_box_type(rect):
                for s in shaded_rects:
                    if rect.intersects(s["rect"]):
                        for btype, color in self.COLORS.items():
                            if s["color"] == color: return btype, s["rect"]
                return None, None

            last_y = 0
            for b in sorted(blocks, key=lambda x: x["bbox"][1]):
                if "lines" not in b: continue
                
                bbox = fitz.Rect(b["bbox"])
                # Filter out headers/footers
                if bbox.y0 < 50 or bbox.y1 > 750: continue
                
                # Check if this block is inside a shaded box
                btype, box_rect = get_box_type(bbox)
                
                block_text = ""
                is_bold = False
                max_size = 0
                for l in b["lines"]:
                    for s in l["spans"]:
                        block_text += s["text"] + " "
                        if "Bold" in s["font"]: is_bold = True
                        max_size = max(max_size, s["size"])
                
                block_text = block_text.strip()
                if not block_text: continue

                # Identify Section Headers (High fidelity)
                # 1.3 style (Section)
                if is_bold and max_size > 13 and re.match(r'^\d+\.\d+(\s|$)', block_text):
                    all_elements.append({"type": "section", "content": block_text, "id": block_text.split()[0]})
                # 1.3.1 style (Subsection)
                elif is_bold and max_size > 11 and re.match(r'^\d+\.\d+\.\d+(\s|$)', block_text):
                    all_elements.append({"type": "subsection", "content": block_text, "id": block_text.split()[0]})
                # arXiv / paper style: "1 Introduction", "2 Background" etc.
                elif is_bold and max_size > 11 and re.match(r'^\d+\s+\w', block_text):
                    all_elements.append({"type": "section", "content": block_text, "id": block_text.split()[0]})
                # Common paper section keywords (bold, no number prefix)
                elif is_bold and max_size > 11 and re.match(
                    r'^(Abstract|Introduction|Background|Related Work|Conclusion|'
                    r'Discussion|Method|Methodology|Experiment|Results?|References?|'
                    r'Appendix|Acknowledgements?)\b',
                    block_text, re.IGNORECASE
                ):
                    slug = block_text.split()[0].lower()
                    all_elements.append({"type": "section", "content": block_text, "id": slug})
                # Shaded Box Block
                elif btype:
                    # Merge multiple text blocks within the same shaded box
                    if all_elements and all_elements[-1].get("box_rect") == box_rect:
                        all_elements[-1]["content"] += " " + block_text
                    else:
                        # Extract label (e.g. Definition 1.21)
                        label_match = re.match(r'^([a-zA-Z]+\s+\d+[\.\d]*)\.?', block_text)
                        label = label_match.group(1) if label_match else ""
                        content = block_text[len(label):].strip() if label else block_text
                        all_elements.append({
                            "type": btype, 
                            "label": label, 
                            "content": content, 
                            "box_rect": box_rect
                        })
                # Normal Text
                else:
                    if all_elements and all_elements[-1]["type"] == "text":
                        all_elements[-1]["content"] += " " + block_text
                    else:
                        all_elements.append({"type": "text", "content": block_text})

        return self.clean_elements(all_elements)

    def clean_elements(self, elements):
        for e in elements:
            e["content"] = re.sub(r'\s+', ' ', e["content"]).strip()
        return [e for e in elements if e["content"]]
