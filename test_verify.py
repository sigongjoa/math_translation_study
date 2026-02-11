#!/usr/bin/env python3
"""
Test script: run verification on existing translated sections and build PDF.
Uses output_test/sections/ as input (already translated data).
"""

import json
import subprocess
import shutil
from pathlib import Path
from verifier import TranslationVerifier
from json_to_latex import generate_full_document

OUTPUT_DIR = Path("output_test")
SECTIONS_DIR = OUTPUT_DIR / "sections"
LATEX_DIR = OUTPUT_DIR / "latex"
VERIFY_MODEL = "qwen3:14b"


def main():
    # ─── Step 1: Init verifier ───
    print("=" * 60)
    print("Verification Test: output_test/sections/")
    print("=" * 60)

    verifier = TranslationVerifier(
        model_name=VERIFY_MODEL,
        verify_types=["formula", "semantic", "logic", "research"],
    )
    if not verifier.test_connection():
        print(f"Model {VERIFY_MODEL} not available, aborting.")
        return

    # ─── Step 2: Load sections ───
    json_files = sorted(SECTIONS_DIR.glob("*.json"))
    print(f"\nFound {len(json_files)} sections to verify")

    sections = {}
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
            sid = data.get("section_id", jf.stem)
            sections[sid] = data

    # ─── Step 3: Run verification ───
    print(f"\nRunning verification with {VERIFY_MODEL}...\n")
    scores = []

    for sid, section_data in sections.items():
        if not section_data.get("content_translated"):
            print(f"  {sid}: no translation, skipping")
            continue

        print(f"  Section {sid}:")
        report = verifier.verify_section(section_data)
        section_data["verification"] = report

        score = report.get("score", 0)
        scores.append(score)
        print(f"    Score: {score} "
              f"(F:{report.get('formula',{}).get('score','-')} "
              f"S:{report.get('semantic',{}).get('score','-')} "
              f"L:{report.get('logic',{}).get('score','-')} "
              f"R:{report.get('research',{}).get('score','-')})")

    if scores:
        avg = sum(scores) / len(scores)
        print(f"\n  Average score: {avg:.1f}")
        low = [(sid, s) for sid, s in zip(sections.keys(), scores) if s < 60]
        if low:
            print(f"  Low-score sections: {low}")

    # ─── Step 3.5: Enrich with educational content ───
    print(f"\nEnriching sections with deep research content...\n")
    for sid, section_data in sections.items():
        if not section_data.get("content_original"):
            continue
        print(f"  Enriching {sid}:")
        enrichments = verifier.enrich_section(section_data)
        if enrichments:
            section_data["enrichments"] = enrichments
            print(f"    → {len(enrichments)} concepts researched")
            for e in enrichments:
                print(f"      - {e['title_ko']}")
        else:
            print(f"    → No enrichments")

    # ─── Step 4: Save updated JSON ───
    print("\nSaving verification results to JSON...")
    for sid, section_data in sections.items():
        out_file = SECTIONS_DIR / f"{sid.replace('.', '_')}.json"
        # Find the right filename (may use _ or .)
        candidates = [
            SECTIONS_DIR / f"{sid}.json",
            SECTIONS_DIR / f"{sid.replace('.', '_')}.json",
        ]
        for c in candidates:
            if c.exists():
                out_file = c
                break

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(section_data, f, ensure_ascii=False, indent=2)

    # ─── Step 5: Generate LaTeX ───
    print("\nGenerating LaTeX...")
    tex_file = LATEX_DIR / "main.tex"
    generate_full_document(
        sections_dir=str(SECTIONS_DIR),
        output_tex=str(tex_file),
        part_label="I",
    )

    # ─── Step 6: Build PDF ───
    print("\nBuilding PDF with XeLaTeX...")
    if tex_file.exists():
        for run in range(2):
            label = "1st pass" if run == 0 else "2nd pass (TOC)"
            print(f"  XeLaTeX {label}...")
            result = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "main.tex"],
                cwd=str(LATEX_DIR),
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                print(f"  XeLaTeX warning/error (may still produce PDF)")

        pdf_file = LATEX_DIR / "main.pdf"
        if pdf_file.exists():
            final_pdf = OUTPUT_DIR / "translated.pdf"
            shutil.copy2(pdf_file, final_pdf)
            size_kb = final_pdf.stat().st_size / 1024
            print(f"\n  PDF generated: {final_pdf} ({size_kb:.0f} KB)")
        else:
            print("  PDF generation failed.")
            # Show last few lines of log
            log_file = LATEX_DIR / "main.log"
            if log_file.exists():
                with open(log_file) as lf:
                    lines = lf.readlines()
                print("  Last 20 lines of log:")
                for line in lines[-20:]:
                    print(f"    {line.rstrip()}")
    else:
        print(f"  LaTeX file not found: {tex_file}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
