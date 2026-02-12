import os
import sys
import argparse
import subprocess

def run_pipeline(vol="I", chapters=None, skip_scrape=False, skip_translate=False):
    """Full Feynman Lectures translation pipeline."""
    if chapters is None:
        chapters = [1]

    from feynman_scraper import FeynmanScraper
    from feynman_parser import FeynmanParser
    from feynman_translator import FeynmanTranslator
    from feynman_enricher import FeynmanEnricher
    from feynman_latex_gen import FeynmanLatexGen
    from feynman_batch_img import batch_convert

    scraper = FeynmanScraper(output_dir="feynman_raw")
    parser = FeynmanParser(raw_dir="feynman_raw", output_dir="feynman_json")
    translator = FeynmanTranslator()
    enricher = FeynmanEnricher()
    latex_gen = FeynmanLatexGen()

    os.makedirs("feynman_translated", exist_ok=True)

    for ch in chapters:
        ch_id = f"{vol}_{ch:02}"
        print(f"\n{'='*60}")
        print(f"  PIPELINE: {ch_id}")
        print(f"{'='*60}")

        # Step 1: Scrape
        if not skip_scrape:
            print("\n[1/8] Scraping HTML...")
            scraper.scrape_chapter(vol, ch)

        # Step 2: Parse
        html_file = f"{ch_id}.html"
        json_file = f"feynman_json/{ch_id}.json"
        if not os.path.exists(json_file):
            print("\n[2/8] Parsing HTML to JSON...")
            parser.parse_file(html_file)
        else:
            print(f"\n[2/8] JSON already exists: {json_file}")

        # Step 3: Download remaining images
        print("\n[3/8] Checking images...")
        # Images are downloaded during parsing, but check for any missing

        # Step 4: Convert SVGZ to PDF
        print("\n[4/8] Converting SVGZ images to PDF...")
        batch_convert("feynman_json/images")

        # Step 5: Translate
        translated_file = f"feynman_translated/{ch_id}_translated.json"
        if not skip_translate and not os.path.exists(translated_file):
            print("\n[5/8] Translating...")
            translator.process_json(json_file, translated_file)
        else:
            print(f"\n[5/8] Translation exists or skipped: {translated_file}")

        # Step 6: Enrich
        enriched_file = f"feynman_translated/{ch_id}_enriched.json"
        if not skip_translate and not os.path.exists(enriched_file):
            print("\n[6/8] Enriching with metadata...")
            enricher.process_json(translated_file, enriched_file)
        else:
            print(f"\n[6/8] Enriched file exists or skipped: {enriched_file}")

        # Step 7: Generate LaTeX
        tex_file = f"feynman_translated/{ch_id}.tex"
        print(f"\n[7/8] Generating LaTeX: {tex_file}")
        import json as json_mod
        with open(enriched_file, "r", encoding="utf-8") as f:
            data = json_mod.load(f)
        latex_gen.save_tex(data, tex_file)

        # Step 8: Compile PDF
        print(f"\n[8/8] Compiling PDF with XeLaTeX...")
        result = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-output-directory=feynman_translated", tex_file],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print(f"[OK] PDF generated: feynman_translated/{ch_id}.pdf")
        else:
            print(f"[WARN] XeLaTeX returned code {result.returncode}")
            # Show last 20 lines of output for debugging
            lines = result.stdout.strip().splitlines()
            for line in lines[-20:]:
                print(f"  {line}")

    print(f"\n{'='*60}")
    print("  PIPELINE COMPLETE")
    print(f"{'='*60}")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Feynman Lectures Full Pipeline")
    p.add_argument("--vol", default="I", help="Volume (I, II, III)")
    p.add_argument("--chapters", type=int, nargs="+", default=[1])
    p.add_argument("--skip-scrape", action="store_true", help="Skip scraping (use existing HTML)")
    p.add_argument("--skip-translate", action="store_true", help="Skip translation (use existing JSON)")
    args = p.parse_args()
    run_pipeline(vol=args.vol, chapters=args.chapters, skip_scrape=args.skip_scrape, skip_translate=args.skip_translate)