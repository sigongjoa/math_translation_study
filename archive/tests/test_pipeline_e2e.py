"""
End-to-end pipeline integration test.

Verifies that all 5 stages + new modules (#12 AnalogyVerifier, #8 CrossReference,
#9 CompanionExplainer) fire correctly with realistic math content sections.

Runs with live Ollama (qwen2.5:7b). Uses a temp DB to avoid polluting pipeline.db.
"""

import json
import os
import tempfile
import unittest

from src.pcm.pipeline.db import PipelineDB
from src.pcm.pipeline.logger import PipelineLogger
from src.pcm.pipeline.stages import (
    Stage1_Orientation,
    Stage2_Drafting,
    Stage3_Refinement,
    Stage4_Validation,
    Stage5_Evolution,
)

# ---------------------------------------------------------------------------
# Realistic math sections (with LaTeX + block types that trigger all modules)
# ---------------------------------------------------------------------------

MATH_SECTIONS = [
    {
        "section_id": "1.1",
        "text": (
            "Definition 1.1 (Group). A group is a set $G$ together with a binary "
            "operation $\\cdot: G \\times G \\to G$ satisfying: "
            "(i) Associativity: $(a \\cdot b) \\cdot c = a \\cdot (b \\cdot c)$ for all $a, b, c \\in G$. "
            "(ii) Identity: there exists $e \\in G$ such that $e \\cdot a = a \\cdot e = a$. "
            "(iii) Inverses: for each $a \\in G$ there exists $a^{-1}$ with $a \\cdot a^{-1} = e$."
        ),
        "block_type": "definition",
    },
    {
        "section_id": "1.2",
        "text": (
            "Theorem 1.2 (Lagrange). If $G$ is a finite group and $H$ is a subgroup of $G$, "
            "then $|H|$ divides $|G|$. "
            "Proof. The left cosets $aH$ partition $G$ into equal-sized classes of size $|H|$. "
            "Hence $|G| = [G:H] \\cdot |H|$. $\\square$"
        ),
        "block_type": "theorem",
    },
    {
        "section_id": "2.1",
        "text": (
            "Definition 2.1 (Ring). A ring $(R, +, \\cdot)$ is an abelian group $(R, +)$ "
            "equipped with an associative multiplication $\\cdot$ that distributes over $+$: "
            "$a \\cdot (b + c) = a \\cdot b + a \\cdot c$ and $(a + b) \\cdot c = a \\cdot c + b \\cdot c$. "
            "Groups arise naturally in rings: the group of units $R^{\\times}$ consists of all "
            "elements $r \\in R$ for which a multiplicative inverse exists."
        ),
        "block_type": "definition",
    },
    {
        "section_id": "2.2",
        "text": (
            "Theorem 2.2 (Chinese Remainder Theorem). Let $m_1, \\ldots, m_k$ be pairwise "
            "coprime positive integers and $M = m_1 \\cdots m_k$. Then "
            "$\\mathbb{Z}/M\\mathbb{Z} \\cong \\mathbb{Z}/m_1\\mathbb{Z} \\times \\cdots "
            "\\times \\mathbb{Z}/m_k\\mathbb{Z}$ as rings. "
            "Proof. The map $x \\mapsto (x \\bmod m_1, \\ldots, x \\bmod m_k)$ is a ring isomorphism."
        ),
        "block_type": "theorem",
    },
]


def run_full_pipeline(sections, db_path):
    """Run all 5 stages on the given sections. Returns final output dict."""
    db = PipelineDB(db_path)

    job_id = db.create_job(pdf_path="test://e2e", start_page=0, end_page=0)
    job = db.get_job(job_id)
    logger = PipelineLogger(db, job_id)

    current_sections = list(sections)

    for StageClass in [Stage1_Orientation, Stage2_Drafting, Stage3_Refinement,
                       Stage4_Validation, Stage5_Evolution]:
        stage_obj = StageClass()
        stage_rec = db.get_or_create_stage(job_id=job_id, stage_num=stage_obj.stage_num,
                                           stage_name=stage_obj.stage_name)
        result = stage_obj.run(job, stage_rec, current_sections, db, logger)
        current_sections = result["sections"]

    output_path = f"results/pipeline_{job['id']}.json"
    with open(output_path) as f:
        return json.load(f), result.get("summary", {})


class TestPipelineE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.makedirs("results", exist_ok=True)
        cls.db_fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        cls.output, cls.summary = run_full_pipeline(MATH_SECTIONS, cls.db_path)

    @classmethod
    def tearDownClass(cls):
        os.close(cls.db_fd)
        try:
            os.unlink(cls.db_path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Basic pipeline checks
    # ------------------------------------------------------------------

    def test_all_sections_processed(self):
        """All 4 input sections should appear in output."""
        self.assertEqual(len(self.output["sections"]), 4)

    def test_all_sections_have_korean_translation(self):
        """Every section must have non-empty final_ko."""
        for sec in self.output["sections"]:
            with self.subTest(section_id=sec["section_id"]):
                self.assertTrue(sec["final_ko"].strip(),
                                f"Section {sec['section_id']} has empty translation")

    def test_translation_contains_korean(self):
        """Translation should contain Korean characters."""
        for sec in self.output["sections"]:
            ko_text = sec["final_ko"]
            has_korean = any('\uAC00' <= ch <= '\uD7A3' for ch in ko_text)
            with self.subTest(section_id=sec["section_id"]):
                self.assertTrue(has_korean,
                                f"Section {sec['section_id']} has no Korean chars: {ko_text[:200]}")

    def test_domains_classified(self):
        """Sections should be classified as algebra (not general)."""
        domains = {sec["section_id"]: sec["domain"] for sec in self.output["sections"]}
        # At least one section should be algebra
        self.assertTrue(any(d == "algebra" for d in domains.values()),
                        f"No algebra domain found: {domains}")

    def test_scores_above_zero(self):
        """TCR should produce non-zero scores."""
        for sec in self.output["sections"]:
            with self.subTest(section_id=sec["section_id"]):
                self.assertGreater(sec["final_score"], 0,
                                   f"Section {sec['section_id']} has zero score")

    def test_abstraction_scores_computed(self):
        """All sections should have computed abstraction scores."""
        for sec in self.output["sections"]:
            with self.subTest(section_id=sec["section_id"]):
                self.assertIn("abstraction_score", sec)
                self.assertIsInstance(sec["abstraction_score"], float)

    # ------------------------------------------------------------------
    # New module checks
    # ------------------------------------------------------------------

    def test_motivation_injected_for_definition_blocks(self):
        """Definition/theorem blocks with high abstraction should get motivation."""
        # Sections 1.1 and 2.1 are definitions with LaTeX formulas → abstraction_score > 0.6
        definition_secs = [s for s in self.output["sections"]
                           if s["block_type"] in ("definition", "theorem")]
        high_abs = [s for s in definition_secs if s["abstraction_score"] >= 0.6]
        injected = [s for s in high_abs if s["motivation_injected"]]

        if high_abs:  # If Ollama responded successfully
            self.assertGreater(len(injected), 0,
                               f"No motivation injected. High-abstraction secs: "
                               f"{[(s['section_id'], s['abstraction_score']) for s in high_abs]}")

    def test_latex_preserved_in_translation(self):
        """LaTeX formulas in original must appear in final_ko (not stripped)."""
        for sec in self.output["sections"]:
            original = sec["original_en"]
            final = sec["final_ko"]
            # Check that $ signs are present (at least partial preservation)
            if original.count("$") >= 2:
                with self.subTest(section_id=sec["section_id"]):
                    self.assertIn("$", final,
                                  f"Section {sec['section_id']}: LaTeX stripped from translation")

    def test_cross_ref_injected_for_related_sections(self):
        """Sections with shared concepts (group/ring) should get cross-ref links."""
        # 1.2 (Lagrange) references groups → should link to 1.1 (Group definition)
        # 2.1 (Ring) references groups → should link to 1.1
        cross_ref_secs = [s for s in self.output["sections"] if s.get("cross_ref_injected")]
        # At least one section should have cross-ref (since group/ring share concepts)
        self.assertGreater(len(cross_ref_secs), 0,
                           "No cross-reference links injected for related algebra sections")

    def test_companion_injected_for_high_abstraction(self):
        """Sections with high abstraction_score should get companion explanation."""
        high_abs = [s for s in self.output["sections"] if s["abstraction_score"] >= 0.5]
        companion_secs = [s for s in high_abs if s.get("companion_injected")]
        if high_abs:
            self.assertGreater(len(companion_secs), 0,
                               f"No companion explanations injected. "
                               f"High-abs sections: {[(s['section_id'], s['abstraction_score']) for s in high_abs]}")

    def test_output_json_saved(self):
        """Pipeline should save output JSON file."""
        self.assertIsNotNone(self.output.get("job_id"))
        self.assertIn("sections", self.output)

    def test_stats_in_output(self):
        """Output JSON should include stats."""
        self.assertIn("stats", self.output)
        self.assertEqual(self.output["stats"]["section_count"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
