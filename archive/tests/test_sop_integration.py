"""
Integration test for #18 — 5단계 통합 SOP (Standard Operating Procedure).

Verifies that MasterPipeline correctly orchestrates all 5 stages end-to-end:
  Stage 1: Domain Orientation   (DomainClassifier, KnowledgeManager)
  Stage 2: Drafting             (TranslationAgent with glossary injection)
  Stage 3: TCR Refinement       (TCR loop, AnalogyVerifier)
  Stage 4: Validation           (ConsistencyManager, CrossReference)
  Stage 5: Evolution            (CompanionExplainer, MotivationAgent, FeedbackLoop)

Uses live Ollama (qwen2.5:7b) + temp SQLite DB.
"""

import json
import os
import tempfile
import unittest

from src.pcm.pipeline.master import MasterPipeline
from src.pcm.pipeline.db import PipelineDB

# ---------------------------------------------------------------------------
# Realistic algebra sections to exercise all 5 stages
# ---------------------------------------------------------------------------

ALGEBRA_SECTIONS = [
    {
        "section_id": "1.1",
        "text": (
            "Definition 1.1 (Group). A group $(G, \\cdot)$ consists of a set $G$ "
            "and a binary operation $\\cdot$ satisfying: "
            "(i) Closure: $a \\cdot b \\in G$ for all $a, b \\in G$. "
            "(ii) Associativity: $(a \\cdot b) \\cdot c = a \\cdot (b \\cdot c)$. "
            "(iii) Identity: $\\exists e \\in G$ such that $e \\cdot a = a$. "
            "(iv) Inverses: $\\forall a \\in G, \\exists a^{-1}$ with $a \\cdot a^{-1} = e$."
        ),
        "block_type": "definition",
    },
    {
        "section_id": "1.2",
        "text": (
            "Theorem 1.2 (Lagrange). Let $G$ be a finite group and $H \\leq G$ a subgroup. "
            "Then $|H|$ divides $|G|$, and the index $[G:H] = |G|/|H|$. "
            "Proof sketch: the left cosets $\\{aH : a \\in G\\}$ partition $G$ into $[G:H]$ "
            "classes of equal size $|H|$."
        ),
        "block_type": "theorem",
    },
    {
        "section_id": "2.1",
        "text": (
            "Definition 2.1 (Ring). A ring $(R, +, \\cdot)$ is an abelian group $(R, +)$ "
            "equipped with an associative multiplication $\\cdot$ that distributes over $+$. "
            "The group of units $R^{\\times}$ generalises the group concept inside a ring."
        ),
        "block_type": "definition",
    },
]


def _run_master(sections, db_path):
    """Run MasterPipeline with sections_override, return (job_id, output_dict)."""
    pipeline = MasterPipeline(db_path=db_path)
    job_id = pipeline.run(
        pdf_path="test://sop",
        start_page=0,
        end_page=0,
        sections_override=sections,
    )
    output_path = f"results/pipeline_{job_id}.json"
    with open(output_path) as f:
        output = json.load(f)
    return job_id, output


class TestSOPIntegration(unittest.TestCase):
    """End-to-end SOP verification via MasterPipeline."""

    @classmethod
    def setUpClass(cls):
        os.makedirs("results", exist_ok=True)
        cls.db_fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        cls.job_id, cls.output = _run_master(ALGEBRA_SECTIONS, cls.db_path)
        cls.sections = cls.output["sections"]

    @classmethod
    def tearDownClass(cls):
        os.close(cls.db_fd)
        try:
            os.unlink(cls.db_path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Stage 1: Domain Orientation
    # ------------------------------------------------------------------

    def test_stage1_domains_classified(self):
        """All sections must have a domain field after Stage 1."""
        for sec in self.sections:
            with self.subTest(section_id=sec["section_id"]):
                self.assertIn("domain", sec)
                self.assertIsNotNone(sec["domain"])

    def test_stage1_algebra_domain_detected(self):
        """At least one section should be classified as algebra."""
        domains = [s["domain"] for s in self.sections]
        self.assertIn("algebra", domains,
                      f"Expected 'algebra' in domains: {domains}")

    # ------------------------------------------------------------------
    # Stage 2: Drafting
    # ------------------------------------------------------------------

    def test_stage2_translation_produced(self):
        """Stage 2 output is reflected in final_ko (Stage 3 builds on Stage 2 draft)."""
        for sec in self.sections:
            with self.subTest(section_id=sec["section_id"]):
                # final_ko is set by Stage 3 from Stage 2's draft_ko
                self.assertIn("final_ko", sec)
                self.assertTrue(sec["final_ko"].strip(),
                                "final_ko (built from draft) is empty")

    def test_stage2_korean_characters_in_final(self):
        """Final translation (originating from Stage 2 draft) contains Korean."""
        for sec in self.sections:
            ko = sec.get("final_ko", "")
            has_korean = any('\uAC00' <= ch <= '\uD7A3' for ch in ko)
            with self.subTest(section_id=sec["section_id"]):
                self.assertTrue(has_korean,
                                f"No Korean chars in final_ko: {ko[:100]}")

    # ------------------------------------------------------------------
    # Stage 3: TCR Refinement
    # ------------------------------------------------------------------

    def test_stage3_final_ko_present(self):
        """Each section must have final_ko after TCR."""
        for sec in self.sections:
            with self.subTest(section_id=sec["section_id"]):
                self.assertIn("final_ko", sec)
                self.assertTrue(sec["final_ko"].strip())

    def test_stage3_tcr_score_positive(self):
        """TCR scoring must produce a positive score."""
        for sec in self.sections:
            with self.subTest(section_id=sec["section_id"]):
                self.assertIn("final_score", sec)
                self.assertGreater(sec["final_score"], 0)

    def test_stage3_abstraction_score_computed(self):
        """Abstraction score must be a float in [0, 1]."""
        for sec in self.sections:
            with self.subTest(section_id=sec["section_id"]):
                self.assertIn("abstraction_score", sec)
                score = sec["abstraction_score"]
                self.assertIsInstance(score, float)
                self.assertGreaterEqual(score, 0.0)
                self.assertLessEqual(score, 1.0)

    def test_stage3_latex_preserved(self):
        """LaTeX formulas must survive into final_ko ($...$ or \\(...\\) are both valid)."""
        for sec in self.sections:
            original = sec.get("original_en") or sec.get("text", "")
            if original.count("$") >= 2:
                final = sec["final_ko"]
                has_latex = "$" in final or "\\(" in final or "\\[" in final
                with self.subTest(section_id=sec["section_id"]):
                    self.assertTrue(has_latex,
                                    f"LaTeX stripped from translation: {final[:100]}")

    # ------------------------------------------------------------------
    # Stage 4: Validation + CrossReference
    # ------------------------------------------------------------------

    def test_stage4_cross_ref_field_set(self):
        """All sections must have cross_ref_injected field after Stage 4 (True or False)."""
        for sec in self.sections:
            with self.subTest(section_id=sec["section_id"]):
                self.assertIn("cross_ref_injected", sec,
                              f"cross_ref_injected field missing from section {sec['section_id']}")
                self.assertIsInstance(sec["cross_ref_injected"], bool)

    # ------------------------------------------------------------------
    # Stage 5: Evolution (CompanionExplainer, MotivationAgent)
    # ------------------------------------------------------------------

    def test_stage5_companion_injected(self):
        """High-abstraction sections should get companion explanation."""
        high_abs = [s for s in self.sections if s.get("abstraction_score", 0) >= 0.5]
        if high_abs:
            injected = [s for s in high_abs if s.get("companion_injected")]
            self.assertGreater(len(injected), 0,
                               f"No companion injected for high-abstraction sections: "
                               f"{[(s['section_id'], s['abstraction_score']) for s in high_abs]}")

    def test_stage5_motivation_injected(self):
        """Definition/theorem blocks should get motivation injection."""
        def_secs = [s for s in self.sections
                    if s.get("block_type") in ("definition", "theorem")]
        if def_secs:
            injected = [s for s in def_secs if s.get("motivation_injected")]
            self.assertGreater(len(injected), 0,
                               "No motivation injected for definition/theorem blocks")

    # ------------------------------------------------------------------
    # Output structure
    # ------------------------------------------------------------------

    def test_output_job_id_matches(self):
        """Output JSON job_id should match the returned job_id."""
        self.assertEqual(self.output.get("job_id"), self.job_id)

    def test_output_section_count(self):
        """Output must contain all 3 input sections."""
        self.assertEqual(len(self.sections), 3)

    def test_output_stats_present(self):
        """Output JSON must include a stats block."""
        self.assertIn("stats", self.output)
        self.assertEqual(self.output["stats"]["section_count"], 3)

    def test_output_file_written(self):
        """Pipeline must have written the results JSON file."""
        output_path = f"results/pipeline_{self.job_id}.json"
        self.assertTrue(os.path.exists(output_path),
                        f"Output file not found: {output_path}")

    # ------------------------------------------------------------------
    # Job resumability (idempotency)
    # ------------------------------------------------------------------

    def test_resumable_job_skips_completed_stages(self):
        """Re-running the same job_id should skip all completed stages (fast)."""
        import time
        pipeline = MasterPipeline(db_path=self.db_path)
        start = time.time()
        returned_id = pipeline.run(
            pdf_path="test://sop",
            start_page=0,
            end_page=0,
            job_id=self.job_id,
            sections_override=ALGEBRA_SECTIONS,
        )
        elapsed = time.time() - start
        self.assertEqual(returned_id, self.job_id)
        # Resuming (all stages completed) should be much faster than a full run
        self.assertLess(elapsed, 30,
                        f"Resume took too long ({elapsed:.1f}s) — stages not being skipped")

    # ------------------------------------------------------------------
    # DB state verification
    # ------------------------------------------------------------------

    def test_db_all_stages_completed(self):
        """All 5 stages should be marked 'completed' in the DB."""
        db = PipelineDB(self.db_path)
        stages = db.get_stages_for_job(self.job_id)
        self.assertEqual(len(stages), 5,
                         f"Expected 5 stage records, got {len(stages)}")
        for stage in stages:
            with self.subTest(stage_num=stage["stage_num"]):
                self.assertEqual(stage["status"], "completed",
                                 f"Stage {stage['stage_num']} not completed: {stage['status']}")

    def test_db_job_status_completed(self):
        """Job status in DB should be 'completed'."""
        db = PipelineDB(self.db_path)
        job = db.get_job(self.job_id)
        self.assertEqual(job["status"], "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
