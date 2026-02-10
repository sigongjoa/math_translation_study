#!/usr/bin/env python3
"""
Main translation pipeline: PDF → Parse → Translate → Supplements → LaTeX → PDF
"""

import json
import argparse
import subprocess
from pathlib import Path
from pdf_parser import PDFParser
from translator import OllamaTranslator
from supplement_generator import SupplementGenerator
from json_to_latex import generate_full_document
from tqdm import tqdm

TOTAL_STEPS = 7


def main():
    parser = argparse.ArgumentParser(description="Translate PDF to Korean LaTeX/PDF")
    parser.add_argument("--input", default="PCM.pdf", help="Input PDF file")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--model", default="gemma2:9b", help="Ollama model for translation")
    parser.add_argument("--supplement-model", default="qwen2.5-coder:7b",
                        help="Ollama model for supplement generation")
    parser.add_argument("--start-page", type=int, default=0, help="Start page (0-indexed)")
    parser.add_argument("--end-page", type=int, default=None, help="End page (0-indexed)")
    parser.add_argument("--test", action="store_true", help="Test mode: process first 3 pages")
    parser.add_argument("--skip-translation", action="store_true", help="Skip translation, only parse")
    parser.add_argument("--skip-polish", action="store_true", help="Skip 2nd pass polishing")
    parser.add_argument("--skip-supplements", action="store_true", help="Skip supplement generation")
    parser.add_argument("--skip-latex", action="store_true", help="Skip LaTeX generation")
    parser.add_argument("--skip-pdf", action="store_true", help="Skip PDF build")
    parser.add_argument("--part", default="I", help="Part label for LaTeX (I, II, etc.)")

    args = parser.parse_args()

    if args.test:
        args.end_page = (args.start_page or 0) + 3
        print("=" * 60)
        print("TEST MODE: Processing 3 pages only")
        print("=" * 60)

    # ─── Step 1: Initialize models ───
    print(f"\n[1/{TOTAL_STEPS}] Initializing models...")

    translator = None
    if not args.skip_translation:
        translator = OllamaTranslator(model_name=args.model)
        if not translator.test_connection():
            print("\nCannot connect to Ollama.")
            print("Please ensure Ollama is running: ollama serve")
            print(f"And model is installed: ollama pull {args.model}")
            return

    supp_generator = None
    if not args.skip_supplements:
        supp_generator = SupplementGenerator(model_name=args.supplement_model)
        if not supp_generator.test_connection():
            print(f"\nSupplement model not available: {args.supplement_model}")
            print("Continuing without supplements...")
            supp_generator = None

    if not translator and not supp_generator:
        print("  Parse-only mode\n")
    print()

    # ─── Step 2: Parse PDF ───
    print(f"[2/{TOTAL_STEPS}] Parsing PDF: {args.input}")
    print(f"  Pages: {args.start_page} to {args.end_page or 'end'}")
    print(f"  Output: {args.output}/\n")

    with PDFParser(args.input, args.output) as pdf_parser:
        sections = pdf_parser.parse_full_document(args.start_page, args.end_page)

        if not sections:
            print("\nNo sections detected, falling back to page-by-page mode...")
            end = args.end_page or len(pdf_parser.doc)
            for page_num in range(args.start_page, min(end, len(pdf_parser.doc))):
                text = pdf_parser.extract_text_from_page(page_num)
                images = pdf_parser.extract_images_from_page(page_num)

                page_data = {
                    "section_id": f"page_{page_num + 1}",
                    "title_original": f"Page {page_num + 1}",
                    "title_translated": f"페이지 {page_num + 1}",
                    "content_original": text,
                    "content_translated": "",
                    "images": images,
                    "page_range": [page_num + 1, page_num + 1],
                    "level": "subsection",
                    "font_size": 8.1,
                    "supplements": {},
                }
                sections[f"page_{page_num + 1}"] = page_data

        print(f"\nFound {len(sections)} sections\n")

        # ─── Step 3: Translate ───
        if translator and not args.skip_translation:
            print(f"[3/{TOTAL_STEPS}] Translating {len(sections)} sections...")
            print(f"  Model: {args.model}")
            print(f"  Polish: {'OFF' if args.skip_polish else 'ON (2-pass)'}\n")

            for section_id, section_data in tqdm(sections.items(),
                                                  desc="Translating", unit="section"):
                sections[section_id] = translator.translate_section(
                    section_data,
                    do_polish=not args.skip_polish
                )
        else:
            print(f"[3/{TOTAL_STEPS}] Skipping translation\n")

        # ─── Step 4: Generate supplements ───
        if supp_generator and not args.skip_supplements:
            print(f"[4/{TOTAL_STEPS}] Generating supplements for {len(sections)} sections...")
            print(f"  Model: {args.supplement_model}\n")

            for section_id, section_data in tqdm(sections.items(),
                                                  desc="Supplements", unit="section"):
                print(f"\n  Section {section_id}:")
                supplements = supp_generator.generate_all_supplements(section_data)
                sections[section_id]["supplements"] = supplements
                print(f"    → Generated: {', '.join(supplements.keys()) if supplements else 'none'}")
        else:
            print(f"[4/{TOTAL_STEPS}] Skipping supplement generation\n")

        # ─── Step 5: Save JSON results ───
        print(f"[5/{TOTAL_STEPS}] Saving results...")
        pdf_parser.save_sections_to_json(sections)
        pdf_parser.save_metadata(sections)

    # ─── Step 6: Generate LaTeX ───
    if not args.skip_latex:
        print(f"\n[6/{TOTAL_STEPS}] Generating LaTeX...")
        latex_output = Path(args.output) / "latex" / "main.tex"
        generate_full_document(
            sections_dir=f"{args.output}/sections",
            output_tex=str(latex_output),
            part_label=args.part,
        )
    else:
        print(f"\n[6/{TOTAL_STEPS}] Skipping LaTeX generation")

    # ─── Step 7: Build PDF ───
    if not args.skip_pdf and not args.skip_latex:
        print(f"\n[7/{TOTAL_STEPS}] Building PDF with XeLaTeX...")
        latex_dir = Path(args.output) / "latex"
        tex_file = latex_dir / "main.tex"

        if tex_file.exists():
            for run in range(2):
                label = "1st pass" if run == 0 else "2nd pass (TOC)"
                print(f"  XeLaTeX {label}...")
                result = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "main.tex"],
                    cwd=str(latex_dir),
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode != 0:
                    print(f"  XeLaTeX warning/error (may still produce PDF)")

            pdf_file = latex_dir / "main.pdf"
            if pdf_file.exists():
                final_pdf = Path(args.output) / "translated.pdf"
                import shutil
                shutil.copy2(pdf_file, final_pdf)
                print(f"\n  PDF generated: {final_pdf}")
            else:
                print("  PDF generation failed. Check LaTeX logs.")
        else:
            print(f"  LaTeX file not found: {tex_file}")
    else:
        print(f"\n[7/{TOTAL_STEPS}] Skipping PDF build")

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print("=" * 60)
    print(f"\nOutput: {args.output}/")
    print(f"  Sections JSON: {args.output}/sections/")
    print(f"  Images:        {args.output}/images/")
    if not args.skip_latex:
        print(f"  LaTeX:         {args.output}/latex/main.tex")
    if not args.skip_pdf:
        print(f"  PDF:           {args.output}/translated.pdf")


if __name__ == "__main__":
    main()
