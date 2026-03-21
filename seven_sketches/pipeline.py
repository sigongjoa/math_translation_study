#!/usr/bin/env python3
"""
Seven Sketches — Master SOP Pipeline v5 (FULL IMPLEMENTATION)
Integrates all previously 'empty' issues into a working engine.
"""

import os
import json
import argparse
from pathlib import Path
from tqdm import tqdm

# Import REAL implementations
from src.pcm.core.structure_analyzer import PDFStructureAnalyzer
from src.pcm.core.glossary_architect import GlossaryArchitect
from src.pcm.core.tcr_loop import TCRLoop
from src.pcm.core.knowledge_manager import KnowledgeManager
from src.pcm.core.wolfram_verifier import WolframVerifier
from src.pcm.core.knowledge_agent import KnowledgeAgent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="results/master_sop_final")
    parser.add_argument("--start-page", type=int, default=21)
    parser.add_argument("--end-page", type=int, default=50)
    parser.add_argument("--model", default="gemma2:9b")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Knowledge Orientation (Issue #10, #16)
    print("--- [SOP Stage 1] Building Dynamic Glossary ---")
    architect = GlossaryArchitect(args.input, model=args.model)
    architect.build_chapter_glossary("seven_sketches", "ch1", args.start_page, args.end_page)
    
    km = KnowledgeManager()
    glossary = km.get_all_for_domain("category_theory") # Uses real knowledge bank

    # 2. Structural Parsing (Issue #15, #11)
    print("--- [SOP Stage 2] Parsing Visual Structure ---")
    analyzer = PDFStructureAnalyzer(args.input)
    elements = analyzer.extract_structure(args.start_page, args.end_page)

    # 3. Intelligent Translation with TCR Loop (Issue #4)
    print("--- [SOP Stage 3] TCR Translation Loop (Threshold: 80) ---")
    tcr = TCRLoop(model=args.model, threshold=80, max_iterations=3)
    wolfram = WolframVerifier()
    
    for e in tqdm(elements, desc="Processing Elements"):
        if e["type"] == "text" or e["type"] in ["definition", "example", "remark"]:
            # Run the REAL TCR Loop with retries
            final_ko, trace = tcr.run(e["content"], glossary, "Translate to academic Korean.")
            e["content_ko"] = final_ko
            e["trace"] = trace
            
            # Unit & Formula Verification (Issue #5)
            is_valid, issues = wolfram.check_unit_consistency(final_ko)
            if not is_valid:
                print(f"   [Warning] Unit inconsistency: {issues}")

    # 4. Save Artifacts
    with open(out_dir / "final_elements.json", "w", encoding="utf-8") as f:
        json.dump(elements, f, ensure_ascii=False, indent=2)
    
    print(f"\n--- MISSION COMPLETE ---")
    print(f"Results saved to {args.output}")

if __name__ == "__main__":
    main()
