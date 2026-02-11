#!/usr/bin/env python3
"""Quick test: run enrichment only on 2 sections, then build PDF with enrichment boxes."""

import json
import subprocess
import shutil
from pathlib import Path
from verifier import TranslationVerifier

SECTIONS_DIR = Path("output_test/sections")
LATEX_DIR = Path("output_test/latex_clean")
VERIFY_MODEL = "qwen3:14b"


def main():
    print("=" * 60)
    print("Quick Enrichment Test")
    print("=" * 60)

    verifier = TranslationVerifier(
        model_name=VERIFY_MODEL,
        verify_types=["formula", "semantic", "logic", "research"],
    )
    if not verifier.test_connection():
        print(f"Model {VERIFY_MODEL} not available.")
        return

    # Load only first 2 sections for quick test
    json_files = sorted(SECTIONS_DIR.glob("*.json"))[:2]
    sections = []
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
            sections.append(data)
        print(f"Loaded: {jf.name} - {data.get('title_original', '')[:50]}")

    # Run enrichment only (skip verification - use existing scores)
    print(f"\nRunning enrichment on {len(sections)} sections...\n")
    for section_data in sections:
        sid = section_data.get("section_id", "?")
        if not section_data.get("content_original"):
            continue
        print(f"  Enriching section {sid}:")
        enrichments = verifier.enrich_section(section_data)
        if enrichments:
            section_data["enrichments"] = enrichments
            print(f"    {len(enrichments)} concepts researched:")
            for e in enrichments:
                print(f"      - {e['title_ko']}")
                print(f"        {e['explanation'][:80]}...")
        else:
            print(f"    No enrichments generated")
        print()

    # Save updated JSON
    print("Saving enriched JSON...")
    for section_data in sections:
        sid = section_data.get("section_id", "")
        for candidate in [SECTIONS_DIR / f"{sid}.json",
                          SECTIONS_DIR / f"{sid.replace('.', '_')}.json"]:
            if candidate.exists():
                with open(candidate, "w", encoding="utf-8") as f:
                    json.dump(section_data, f, ensure_ascii=False, indent=2)
                print(f"  Saved {candidate.name}")
                break

    # Build PDF with all sections (including enrichments from updated JSON)
    print("\nBuilding PDF...")
    from test_verify_clean import main as build_pdf
    build_pdf()


if __name__ == "__main__":
    main()
