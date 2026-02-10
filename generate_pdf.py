#!/usr/bin/env python3
"""
Generate PDF from translated JSON files
"""

import json
from pathlib import Path
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image as RLImage
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from tqdm import tqdm
import os


class PDFGenerator:
    def __init__(self, output_pdf: str = "translated_output.pdf"):
        self.output_pdf = output_pdf
        self.doc = SimpleDocTemplate(
            output_pdf,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )
        
        # Register Korean font (NanumGothic)
        font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        font_bold_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
        
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont('NanumGothic', font_path))
            pdfmetrics.registerFont(TTFont('NanumGothic-Bold', font_bold_path))
            self.font_name = 'NanumGothic'
            self.font_bold_name = 'NanumGothic-Bold'
        else:
            # Fallback to CID font if TTF is not found
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont('HeiseiMin-W3'))
            self.font_name = 'HeiseiMin-W3'
            self.font_bold_name = 'HeiseiMin-W3'
        
        # Create custom styles
        self.styles = getSampleStyleSheet()
        
        # Title style
        self.styles.add(ParagraphStyle(
            name='KoreanTitle',
            parent=self.styles['Heading1'],
            fontName=self.font_bold_name,
            fontSize=16,
            leading=20,
            spaceAfter=12,
        ))
        
        # Body style
        self.styles.add(ParagraphStyle(
            name='KoreanBody',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=10,
            leading=14,
            spaceAfter=6,
            alignment=TA_LEFT,
        ))
        
        # Section ID style
        self.styles.add(ParagraphStyle(
            name='SectionID',
            parent=self.styles['Normal'],
            fontName=self.font_bold_name,
            fontSize=12,
            leading=16,
            textColor='blue',
            spaceAfter=6,
        ))
        
        self.story = []
    
    def add_section(self, section_data: dict):
        """Add a section to the PDF"""
        
        # Section ID
        section_id = section_data.get('section_id', 'Unknown')
        self.story.append(Paragraph(f"섹션 {section_id}", self.styles['SectionID']))
        self.story.append(Spacer(1, 0.1*inch))
        
        # Title
        title_translated = section_data.get('title_translated', '')
        if title_translated:
            self.story.append(Paragraph(title_translated, self.styles['KoreanTitle']))
            self.story.append(Spacer(1, 0.1*inch))
        
        # Content
        content_translated = section_data.get('content_translated', '')
        if content_translated:
            # Split into paragraphs
            paragraphs = content_translated.split('\n\n')
            for para in paragraphs:
                if para.strip():
                    # Clean up text for reportlab
                    para_clean = para.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    self.story.append(Paragraph(para_clean, self.styles['KoreanBody']))
                    self.story.append(Spacer(1, 0.05*inch))
        
        # Images
        images = section_data.get('images', [])
        for img_data in images:
            img_path = img_data.get('path', '')
            if img_path and Path(img_path).exists():
                try:
                    # Add image with max width
                    img = RLImage(img_path, width=4*inch, height=3*inch, kind='proportional')
                    self.story.append(Spacer(1, 0.1*inch))
                    self.story.append(img)
                    self.story.append(Spacer(1, 0.1*inch))
                except Exception as e:
                    print(f"Warning: Could not add image {img_path}: {e}")
        
        # Page break after each section
        self.story.append(PageBreak())
    
    def generate_from_directory(self, sections_dir: str):
        """Generate PDF from all JSON files in directory"""
        sections_path = Path(sections_dir)
        
        if not sections_path.exists():
            print(f"Error: Directory {sections_dir} does not exist")
            return
        
        # Get all JSON files
        json_files = sorted(sections_path.glob('*.json'))
        
        if not json_files:
            print(f"Error: No JSON files found in {sections_dir}")
            return
        
        print(f"Found {len(json_files)} sections to process")
        
        # Add title page
        title_style = ParagraphStyle(
            name='PDFTitle',
            parent=self.styles['Title'],
            fontName=self.font_bold_name,
            fontSize=24,
            leading=28,
            alignment=TA_CENTER,
        )
        
        self.story.append(Spacer(1, 2*inch))
        self.story.append(Paragraph("프린스턴 수학 동반서", title_style))
        self.story.append(Spacer(1, 0.2*inch))
        self.story.append(Paragraph("한글 번역본 (페이지 76-100)", self.styles['KoreanBody']))
        self.story.append(PageBreak())
        
        # Process each section
        for json_file in tqdm(json_files, desc="Generating PDF", unit="section"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    section_data = json.load(f)
                    self.add_section(section_data)
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
        
        # Build PDF
        print(f"\nBuilding PDF: {self.output_pdf}")
        self.doc.build(self.story)
        print(f"✅ PDF generated successfully: {self.output_pdf}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate PDF from translated JSON files")
    parser.add_argument("--sections-dir", default="output/sections", help="Directory containing JSON files")
    parser.add_argument("--output", default="translated_pages_76-100.pdf", help="Output PDF filename")
    
    args = parser.parse_args()
    
    generator = PDFGenerator(args.output)
    generator.generate_from_directory(args.sections_dir)


if __name__ == "__main__":
    main()
