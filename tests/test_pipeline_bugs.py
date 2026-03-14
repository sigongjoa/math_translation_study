"""
Tests for bugs #21-#26 — domain classifier, translation prompt,
TCR evaluator, structure parser, LaTeX output.

All LLM calls are mocked — runs without Ollama.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# #21 / #22  DomainClassifier model + CS/AI domains
# ---------------------------------------------------------------------------

class TestDomainClassifierModel(unittest.TestCase):
    """#21 — DomainClassifier must use _DEFAULT_MODEL, not qwen3:14b"""

    def test_default_model_is_not_qwen3(self):
        from src.pcm.core.wsd_agent import DomainClassifier
        from src.pcm.core.llm_client import _DEFAULT_MODEL
        dc = DomainClassifier()
        self.assertEqual(dc.model_name, _DEFAULT_MODEL)
        self.assertNotEqual(dc.model_name, "qwen3:14b")

    def test_custom_model_accepted(self):
        from src.pcm.core.wsd_agent import DomainClassifier
        dc = DomainClassifier(model_name="llama3:8b")
        self.assertEqual(dc.model_name, "llama3:8b")


class TestDomainClassifierCSAI(unittest.TestCase):
    """#22 — CS/AI/ML domains must exist and classify correctly"""

    def setUp(self):
        from src.pcm.core.wsd_agent import DomainClassifier
        self.dc = DomainClassifier()

    def test_cs_ai_domains_in_list(self):
        self.assertIn("machine_learning", self.dc.DOMAINS)
        self.assertIn("computer_science", self.dc.DOMAINS)
        self.assertIn("nlp", self.dc.DOMAINS)

    def test_cs_keywords_in_domain_keywords(self):
        kws = self.dc.DOMAIN_KEYWORDS
        self.assertIn("machine_learning", kws)
        self.assertIn("computer_science", kws)
        self.assertIn("nlp", kws)

    def test_fallback_classifies_ml_text(self):
        text = (
            "We fine-tune a large language model using reinforcement learning "
            "and benchmark on standard NLP datasets. The transformer architecture "
            "achieves state-of-the-art results."
        )
        domain = self.dc._fallback_classify(text)
        self.assertIn(domain, {"machine_learning", "nlp", "computer_science"})

    def test_fallback_classifies_cs_text(self):
        text = "The algorithm runs in O(n log n) using a balanced binary tree data structure."
        domain = self.dc._fallback_classify(text)
        self.assertEqual(domain, "computer_science")

    @patch("requests.post")
    def test_llm_classify_cs_domain(self, mock_post):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"response": "machine_learning"}
        mock_post.return_value = m
        domain = self.dc.classify("We train a neural network on ImageNet.")
        self.assertEqual(domain, "machine_learning")

    @patch("requests.post")
    def test_llm_failure_falls_back_to_keyword(self, mock_post):
        import requests as req
        mock_post.side_effect = req.RequestException("down")
        text = "The transformer model uses attention mechanism for language understanding."
        domain = self.dc.classify(text)
        self.assertIn(domain, {"machine_learning", "nlp", "computer_science"})


# ---------------------------------------------------------------------------
# #23  Stage2 domain-aware prompts
# ---------------------------------------------------------------------------

class TestStage2DomainPrompt(unittest.TestCase):
    """#23 — Stage2 must use different prompts for different domains"""

    def setUp(self):
        from src.pcm.pipeline.stages import Stage2_Drafting
        self.stage = Stage2_Drafting()

    def test_ml_domain_uses_ai_prompt(self):
        system, instruction = self.stage._get_domain_prompt("machine_learning")
        self.assertNotIn("수학/물리", system)
        self.assertIn("AI", system + instruction)

    def test_cs_domain_uses_cs_prompt(self):
        system, instruction = self.stage._get_domain_prompt("computer_science")
        self.assertNotIn("수학/물리", system)
        self.assertIn("컴퓨터", system + instruction)

    def test_nlp_domain_uses_nlp_prompt(self):
        system, instruction = self.stage._get_domain_prompt("nlp")
        self.assertNotIn("수학/물리", system)
        self.assertIn("NLP", system + instruction)

    def test_algebra_domain_uses_math_prompt(self):
        system, instruction = self.stage._get_domain_prompt("algebra")
        self.assertIn("수학/물리", system)

    def test_general_domain_uses_general_prompt(self):
        system, instruction = self.stage._get_domain_prompt("general")
        self.assertNotIn("수학/물리", system)

    @patch("src.pcm.core.llm_client.requests.post")
    def test_translate_passes_domain_to_prompt(self, mock_post):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"response": "인공지능 에이전트"}
        mock_post.return_value = m

        result = self.stage._translate("AI agents", "", "machine_learning")
        self.assertEqual(result, "인공지능 에이전트")

        # Check the prompt sent to LLM doesn't say 수학/물리
        payload = mock_post.call_args[1]["json"]
        self.assertNotIn("수학/물리", payload["prompt"])

    @patch("src.pcm.core.llm_client.requests.post")
    def test_translate_math_domain_uses_math_prompt(self, mock_post):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"response": "군론"}
        mock_post.return_value = m

        self.stage._translate("group theory", "", "algebra")
        payload = mock_post.call_args[1]["json"]
        self.assertIn("수학/물리", payload["prompt"])


# ---------------------------------------------------------------------------
# #24  TCR evaluator
# ---------------------------------------------------------------------------

class TestTCREvaluator(unittest.TestCase):
    """#24 — TCR evaluator must detect untranslated English and score low"""

    def setUp(self):
        from src.pcm.core.tcr_loop import TCRLoop
        self.tcr = TCRLoop()

    @patch("src.pcm.core.llm_client.requests.post")
    def test_english_translation_gets_low_score(self, mock_post):
        """If LLM returns English as translated text, score must be ≤ 30"""
        # LLM returns 20 for English-only ko
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"message": {"content": '{"score": 15, "critique": "번역 미완료"}'}}
        mock_post.return_value = m

        score, critique = self.tcr._evaluate(
            "Hello world",
            "Hello world",  # Not translated
            {}
        )
        self.assertLessEqual(score, 30)

    @patch("src.pcm.core.llm_client.requests.post")
    def test_korean_translation_can_score_high(self, mock_post):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"message": {"content": '{"score": 90, "critique": "완벽한 번역"}'}}
        mock_post.return_value = m

        score, critique = self.tcr._evaluate(
            "Hello world",
            "안녕하세요 세계",
            {}
        )
        self.assertGreaterEqual(score, 80)
        self.assertEqual(critique, "완벽한 번역")

    def test_heuristic_fallback_english_only(self):
        """Heuristic: all-English ko → score=20"""
        from src.pcm.core.tcr_loop import TCRLoop
        tcr = TCRLoop()
        # Simulate JSON parse failure path by calling with bad LLM
        with patch("src.pcm.core.llm_client.requests.post") as mp:
            mp.return_value = MagicMock()
            mp.return_value.raise_for_status = MagicMock()
            mp.return_value.json.return_value = {"message": {"content": "not json at all"}}
            score, critique = tcr._evaluate(
                "The cat sat on the mat.",
                "The cat sat on the mat.",
                {}
            )
        self.assertLessEqual(score, 30)

    def test_heuristic_fallback_korean_text(self):
        """Heuristic: mostly-Korean ko → score=50 (parsing failed but not penalised)"""
        with patch("src.pcm.core.llm_client.requests.post") as mp:
            mp.return_value = MagicMock()
            mp.return_value.raise_for_status = MagicMock()
            mp.return_value.json.return_value = {"message": {"content": "not json"}}
            from src.pcm.core.tcr_loop import TCRLoop
            tcr = TCRLoop()
            score, _ = tcr._evaluate("text", "고양이가 매트 위에 앉았습니다.", {})
        self.assertEqual(score, 50)

    @patch("src.pcm.core.llm_client.requests.post")
    def test_markdown_wrapped_json_parsed(self, mock_post):
        """LLM wraps JSON in ```json ... ``` — must still parse"""
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            "message": {"content": '```json\n{"score": 75, "critique": "좋음"}\n```'}
        }
        mock_post.return_value = m

        from src.pcm.core.tcr_loop import TCRLoop
        tcr = TCRLoop()
        score, critique = tcr._evaluate("text", "번역", {})
        self.assertEqual(score, 75)

    @patch("src.pcm.core.llm_client.requests.post")
    def test_score_clamped_to_100(self, mock_post):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {"message": {"content": '{"score": 150, "critique": "over"}'}}
        mock_post.return_value = m

        from src.pcm.core.tcr_loop import TCRLoop
        tcr = TCRLoop()
        score, _ = tcr._evaluate("t", "k", {})
        self.assertEqual(score, 100)


# ---------------------------------------------------------------------------
# #25  PDFStructureAnalyzer arXiv headers
# ---------------------------------------------------------------------------

class TestStructureAnalyzerArXiv(unittest.TestCase):
    """#25 — Structure analyzer must recognize arXiv-style section headers"""

    def setUp(self):
        from src.pcm.core.structure_analyzer import PDFStructureAnalyzer
        self.SA = PDFStructureAnalyzer

    def _make_mock_page(self, blocks):
        """Build a minimal fitz-like mock page."""
        mock_page = MagicMock()
        mock_page.get_drawings.return_value = []
        mock_page.get_text.return_value = {"blocks": blocks}
        return mock_page

    def _make_block(self, text, bold=True, size=14.0, y=100):
        span = {"text": text, "font": "Bold" if bold else "Regular", "size": size}
        line = {"spans": [span]}
        block = {
            "lines": [line],
            "bbox": (50, y, 500, y + size + 2),
        }
        return block

    @patch("fitz.open")
    def test_arxiv_numeric_section_detected(self, mock_fitz):
        """'1 Introduction' style must be recognized as a section"""
        mock_doc = MagicMock()
        mock_fitz.return_value = mock_doc
        mock_doc.__getitem__ = MagicMock(return_value=self._make_mock_page([
            self._make_block("1 Introduction", bold=True, size=14),
            self._make_block("This paper presents...", bold=False, size=10, y=120),
        ]))

        analyzer = self.SA("dummy.pdf")
        elements = analyzer.extract_structure(0, 1)

        types = [e["type"] for e in elements]
        self.assertIn("section", types)

    @patch("fitz.open")
    def test_keyword_section_detected(self, mock_fitz):
        """'Abstract', 'Introduction' keywords (bold) must be sections"""
        mock_doc = MagicMock()
        mock_fitz.return_value = mock_doc
        mock_doc.__getitem__ = MagicMock(return_value=self._make_mock_page([
            self._make_block("Abstract", bold=True, size=13),
            self._make_block("We propose a new method...", bold=False, size=10, y=120),
        ]))

        analyzer = self.SA("dummy.pdf")
        elements = analyzer.extract_structure(0, 1)

        types = [e["type"] for e in elements]
        self.assertIn("section", types)

    @patch("fitz.open")
    def test_existing_book_style_still_works(self, mock_fitz):
        """Existing '1.3 style' sections must still be detected"""
        mock_doc = MagicMock()
        mock_fitz.return_value = mock_doc
        mock_doc.__getitem__ = MagicMock(return_value=self._make_mock_page([
            self._make_block("1.3 Lie Groups", bold=True, size=14),
        ]))

        analyzer = self.SA("dummy.pdf")
        elements = analyzer.extract_structure(0, 1)
        types = [e["type"] for e in elements]
        self.assertIn("section", types)


# ---------------------------------------------------------------------------
# #26  LaTeX output generation
# ---------------------------------------------------------------------------

class TestLaTeXOutput(unittest.TestCase):
    """#26 — Stage5 must produce a .tex file alongside JSON"""

    def _make_output(self):
        return {
            "job_id": "test_job",
            "pdf_path": "test.pdf",
            "pages": "0-5",
            "sections": [
                {
                    "section_id": "intro",
                    "original_en": "Introduction to category theory.",
                    "final_ko": "범주론 소개.",
                    "domain": "category_theory",
                    "final_score": 88.0,
                },
                {
                    "section_id": "ch1",
                    "original_en": "A functor is a map between categories.",
                    "final_ko": "함자는 범주 사이의 사상이다.",
                    "domain": "category_theory",
                    "final_score": 92.0,
                },
            ],
        }

    def test_tex_file_created(self):
        from src.pcm.pipeline.stages import Stage5_Evolution
        stage = Stage5_Evolution()
        job = {"id": "test_job", "pdf_path": "test.pdf"}
        output = self._make_output()

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            os.makedirs("results", exist_ok=True)
            try:
                tex_path = stage._write_latex(output, job)
                self.assertTrue(os.path.exists(tex_path))
            finally:
                os.chdir(original_cwd)

    def test_tex_contains_korean(self):
        from src.pcm.pipeline.stages import Stage5_Evolution
        stage = Stage5_Evolution()
        job = {"id": "test_job", "pdf_path": "test.pdf"}
        output = self._make_output()

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "results"), exist_ok=True)
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                tex_path = stage._write_latex(output, job)
                content = open(tex_path, encoding="utf-8").read()
                self.assertIn("범주론", content)
                self.assertIn("함자", content)
            finally:
                os.chdir(original_cwd)

    def test_tex_contains_original_english(self):
        from src.pcm.pipeline.stages import Stage5_Evolution
        stage = Stage5_Evolution()
        job = {"id": "test_job", "pdf_path": "test.pdf"}
        output = self._make_output()

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "results"), exist_ok=True)
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                tex_path = stage._write_latex(output, job)
                content = open(tex_path, encoding="utf-8").read()
                self.assertIn("Introduction to category theory", content)
            finally:
                os.chdir(original_cwd)

    def test_tex_valid_latex_structure(self):
        from src.pcm.pipeline.stages import Stage5_Evolution
        stage = Stage5_Evolution()
        job = {"id": "test_job", "pdf_path": "test.pdf"}
        output = self._make_output()

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "results"), exist_ok=True)
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                tex_path = stage._write_latex(output, job)
                content = open(tex_path, encoding="utf-8").read()
                self.assertIn(r"\begin{document}", content)
                self.assertIn(r"\end{document}", content)
                # xelatex Korean setup (kotex replaced by xeCJK)
                self.assertIn(r"\usepackage{xeCJK}", content)
                self.assertIn("CJK KR", content)
            finally:
                os.chdir(original_cwd)

    def test_tex_escape_special_chars(self):
        from src.pcm.pipeline.stages import _tex_escape
        self.assertEqual(_tex_escape("100% done"), r"100\% done")
        self.assertEqual(_tex_escape("a & b"), r"a \& b")
        self.assertEqual(_tex_escape("$x^2$"), r"\$x\textasciicircum{}2\$")

    @patch("src.pcm.core.llm_client.requests.post")
    def test_stage5_run_produces_tex_path(self, mock_post):
        """Stage5.run() must return tex_path in its result."""
        from src.pcm.pipeline.stages import Stage5_Evolution

        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status = MagicMock()
        mock_post.return_value.json.return_value = {"message": {"content": "설명"}}

        stage = Stage5_Evolution()
        job = {"id": "tex_test_job", "pdf_path": "dummy.pdf", "start_page": 0, "end_page": 1}
        stage_rec = {"id": "stage_1"}
        sections = [
            {
                "section_id": "s1",
                "text": "Category theory is the study of structure.",
                "final_ko": "범주론은 구조를 연구합니다.",
                "domain": "category_theory",
                "final_score": 90.0,
                "db_section_id": "s1",
                "block_type": "body",
                "abstraction_score": 0.1,
            }
        ]

        db = MagicMock()
        db.update_section = MagicMock()
        logger = MagicMock()
        logger.bind.return_value = logger

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            os.makedirs("results", exist_ok=True)
            try:
                result = stage.run(job, stage_rec, sections, db, logger)
                self.assertIn("tex_path", result)
                self.assertIn("pdf_path", result)
                self.assertTrue(result["tex_path"].endswith(".tex"))
                self.assertTrue(os.path.exists(result["tex_path"]))
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
