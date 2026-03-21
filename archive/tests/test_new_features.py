"""
Tests for issues #12 (AnalogyVerifier), #8 (CrossReference), #9 (CompanionExplainer).

All LLM calls are mocked so the suite runs without Ollama.
"""

import unittest
from unittest.mock import patch, MagicMock

from src.pcm.core.analogy_verifier import AnalogyVerifier, VerificationResult, MisconceptionEntry
from src.pcm.core.cross_reference import LinkageAnalyzer, SectionInfo, extract_concepts_from_text
from src.pcm.core.companion_explainer import CompanionExplainer, ExplanationResult


# ============================================================
# Issue #12 — AnalogyVerifier
# ============================================================

class TestAnalogyVerifierMisconceptions(unittest.TestCase):
    """Tests for the built-in misconception dictionary check (no LLM)."""

    def setUp(self):
        self.verifier = AnalogyVerifier()

    def test_infinity_misconception_rejected(self):
        """'무한은 매우 큰 수' pattern → FAIL immediately."""
        result = self.verifier.verify(
            analogy_text="무한은 매우 큰 수입니다.",
            formal_definition="For all n ∈ ℕ there exists m ∈ ℕ with m > n.",
            domain="analysis",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.level, "FAIL")
        self.assertEqual(result.score, 0)
        self.assertIsNotNone(result.flagged_misconception)

    def test_limit_misconception_rejected(self):
        """'극한에 도달' pattern → FAIL immediately."""
        result = self.verifier.verify(
            analogy_text="극한은 함수가 특정 값에 도달하는 것입니다.",
            formal_definition="lim_{x→a} f(x) = L",
            domain="analysis",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.level, "FAIL")

    def test_continuity_misconception_rejected(self):
        """'연속은 끊기지 않은' pattern → FAIL immediately."""
        result = self.verifier.verify(
            analogy_text="연속 함수는 그래프가 끊기지 않고 이어진 함수입니다.",
            formal_definition="f is continuous at a if for all ε>0 there exists δ>0...",
            domain="analysis",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.level, "FAIL")

    def test_vector_space_misconception_rejected(self):
        """'벡터는 화살표' pattern → FAIL immediately."""
        result = self.verifier.verify(
            analogy_text="벡터란 화살표와 같습니다.",
            formal_definition="A vector space V over field F satisfies 8 axioms.",
            domain="linear_algebra",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.level, "FAIL")

    def test_valid_analogy_passes_misconception_check(self):
        """A safe analogy should NOT be flagged by misconception check."""
        # This still goes to LLM — we mock LLM to return score 85
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"response": "SCORE: 85\nREASON: 수학적으로 정확함"}
            mock_post.return_value = mock_resp

            result = self.verifier.verify(
                analogy_text="위상 공간은 '가깝다'는 개념을 추상화한 구조입니다.",
                formal_definition="A topological space (X, τ) where τ satisfies...",
                domain="topology",
            )
        self.assertTrue(result.passed)
        self.assertIsNone(result.flagged_misconception)

    def test_custom_misconception_entry(self):
        """Custom misconception entries are respected."""
        custom = [
            MisconceptionEntry(
                concept="test_concept",
                bad_pattern=r"테스트.*오류",
                why_wrong="이건 테스트 오류 패턴입니다.",
            )
        ]
        verifier = AnalogyVerifier(misconceptions=custom)
        result = verifier.verify(
            analogy_text="테스트 오류 패턴 입니다.",
            formal_definition="...",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.flagged_misconception, "test_concept")


class TestAnalogyVerifierScoring(unittest.TestCase):
    """Tests for LLM-based scoring and decision logic."""

    def setUp(self):
        self.verifier = AnalogyVerifier()

    def _make_mock_response(self, score: int, reason: str = "테스트 이유"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": f"SCORE: {score}\nREASON: {reason}"}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_score_above_70_returns_pass(self):
        """Score >= 70 → PASS, analogy unchanged."""
        with patch("requests.post", return_value=self._make_mock_response(80)):
            result = self.verifier.verify(
                "좋은 비유입니다.",
                "formal def",
                "algebra",
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.level, "PASS")
        self.assertEqual(result.analogy, "좋은 비유입니다.")

    def test_score_between_50_and_70_returns_warn(self):
        """50 <= score < 70 → WARN, scope limiter prepended."""
        with patch("requests.post", return_value=self._make_mock_response(60)):
            result = self.verifier.verify(
                "괜찮은 비유입니다.",
                "formal def",
                "algebra",
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.level, "WARN")
        self.assertIn(AnalogyVerifier.SCOPE_LIMITER_PREFIX, result.analogy)
        self.assertIn("괜찮은 비유입니다.", result.analogy)

    def test_score_below_50_returns_fail(self):
        """Score < 50 → FAIL, analogy unchanged."""
        with patch("requests.post", return_value=self._make_mock_response(30)):
            result = self.verifier.verify(
                "나쁜 비유입니다.",
                "formal def",
                "algebra",
            )
        self.assertFalse(result.passed)
        self.assertEqual(result.level, "FAIL")
        self.assertEqual(result.analogy, "나쁜 비유입니다.")

    def test_llm_unavailable_defaults_to_pass(self):
        """When LLM is down, default score (75) results in PASS."""
        with patch("requests.post", side_effect=Exception("connection refused")):
            result = self.verifier.verify(
                "어떤 비유입니다.",
                "formal def",
                "analysis",
            )
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 75)

    def test_parse_score_from_malformed_response(self):
        """Score parser should handle malformed LLM output gracefully."""
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"response": "이 비유는 좋습니다. 점수: 82점"}
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            result = self.verifier.verify("비유", "정의", "topology")
        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)

    def test_verify_and_fix_retries_on_fail(self):
        """verify_and_fix retries up to MAX_RETRIES when FAIL."""
        call_count = {"n": 0}
        responses = [
            MagicMock(json=MagicMock(return_value={"response": "SCORE: 20\nREASON: 나쁨"}),
                      raise_for_status=MagicMock()),
            MagicMock(json=MagicMock(return_value={"response": "SCORE: 20\nREASON: 여전히 나쁨"}),
                      raise_for_status=MagicMock()),
            MagicMock(json=MagicMock(return_value={"response": "SCORE: 85\nREASON: 이제 좋음"}),
                      raise_for_status=MagicMock()),
        ]

        def side_effect(*args, **kwargs):
            r = responses[call_count["n"] % len(responses)]
            call_count["n"] += 1
            return r

        def regen():
            return "개선된 비유"

        with patch("requests.post", side_effect=side_effect):
            result = self.verifier.verify_and_fix(
                "나쁜 비유", "정의", "algebra", regenerate_fn=regen
            )

        self.assertTrue(result.passed)

    def test_verify_and_fix_exhausts_retries(self):
        """verify_and_fix returns FAIL with warning when retries exhausted."""
        fail_resp = MagicMock(
            json=MagicMock(return_value={"response": "SCORE: 10\nREASON: 매우 나쁨"}),
            raise_for_status=MagicMock()
        )

        with patch("requests.post", return_value=fail_resp):
            result = self.verifier.verify_and_fix(
                "나쁜 비유", "정의", "algebra",
                regenerate_fn=lambda: "또 다른 나쁜 비유"
            )

        self.assertFalse(result.passed)
        self.assertIn("최대 재시도", result.reason)


# ============================================================
# Issue #8 — CrossReference / LinkageAnalyzer
# ============================================================

class TestExtractConceptsFromText(unittest.TestCase):
    """Tests for the regex-based concept extractor."""

    def test_extracts_korean_math_terms(self):
        """Korean math compound terms are extracted."""
        text = "위상 공간에서 열린집합의 성질을 이용해 연속 함수를 정의합니다."
        concepts = extract_concepts_from_text(text)
        self.assertTrue(any("공간" in c or "집합" in c or "함수" in c for c in concepts))

    def test_extracts_from_empty_text(self):
        """Empty text returns empty list."""
        self.assertEqual(extract_concepts_from_text(""), [])

    def test_respects_max_concepts(self):
        """Result list length does not exceed max_concepts."""
        long_text = " ".join([f"위상공간{i}" for i in range(50)])
        concepts = extract_concepts_from_text(long_text, max_concepts=10)
        self.assertLessEqual(len(concepts), 10)


class TestLinkageAnalyzerBuildMap(unittest.TestCase):
    """Tests for reference map construction."""

    def setUp(self):
        self.analyzer = LinkageAnalyzer()
        self.sections = [
            SectionInfo(id="1.2", title="군(Group)", key_concepts=["군", "항등원", "역원"]),
            SectionInfo(id="2.1", title="환(Ring)", key_concepts=["환", "군", "분배법칙"]),
            SectionInfo(id="3.1", title="체(Field)", key_concepts=["체", "환", "역원"]),
        ]
        self.analyzer.build_reference_map(self.sections)

    def test_backward_link_detected(self):
        """Section 2.1 (Ring) should have backward link to 1.2 (Group) via '군'."""
        backward = self.analyzer._ref_map["2.1"]["backward"]
        target_ids = [l.target_section_id for l in backward]
        self.assertIn("1.2", target_ids)

    def test_forward_link_detected(self):
        """Section 1.2 (Group) should have forward link to 2.1 (Ring) via '군'."""
        forward = self.analyzer._ref_map["1.2"]["forward"]
        target_ids = [l.target_section_id for l in forward]
        self.assertIn("2.1", target_ids)

    def test_no_self_reference(self):
        """A section should never reference itself."""
        for section_id in ["1.2", "2.1", "3.1"]:
            all_refs = (
                self.analyzer._ref_map[section_id]["backward"]
                + self.analyzer._ref_map[section_id]["forward"]
            )
            for link in all_refs:
                self.assertNotEqual(link.target_section_id, section_id)

    def test_no_references_for_isolated_section(self):
        """Section with no shared concepts has no references."""
        sections = [
            SectionInfo(id="1.1", title="A", key_concepts=["개념A"]),
            SectionInfo(id="1.2", title="B", key_concepts=["개념B"]),  # disjoint
        ]
        analyzer = LinkageAnalyzer()
        analyzer.build_reference_map(sections)
        self.assertEqual(analyzer._ref_map["1.1"]["forward"], [])
        self.assertEqual(analyzer._ref_map["1.2"]["backward"], [])

    def test_shared_concepts_populated(self):
        """Shared concepts between 1.2 and 2.1 should include '군'."""
        backward_links = self.analyzer._ref_map["2.1"]["backward"]
        link_to_12 = next((l for l in backward_links if l.target_section_id == "1.2"), None)
        self.assertIsNotNone(link_to_12)
        self.assertIn("군", link_to_12.shared_concepts)

    def test_validate_section_references_no_invalid(self):
        """validate_section_references returns empty list for valid map."""
        for s in self.sections:
            invalid = self.analyzer.validate_section_references(s.id)
            self.assertEqual(invalid, [], f"Section {s.id} has invalid references: {invalid}")

    def test_rebuild_map_resets_state(self):
        """Calling build_reference_map again with new data resets old state."""
        new_sections = [
            SectionInfo(id="9.1", title="X", key_concepts=["새개념"]),
        ]
        self.analyzer.build_reference_map(new_sections)
        self.assertNotIn("1.2", self.analyzer._ref_map)
        self.assertIn("9.1", self.analyzer._ref_map)


class TestLinkageAnalyzerGeneration(unittest.TestCase):
    """Tests for backward/forward LaTeX generation."""

    def setUp(self):
        self.analyzer = LinkageAnalyzer()
        sections = [
            SectionInfo(id="1.2", title="군(Group)", key_concepts=["군", "항등원"]),
            SectionInfo(id="2.1", title="환(Ring)", key_concepts=["환", "군", "분배법칙"]),
        ]
        self.analyzer.build_reference_map(sections)

    def _mock_llm(self, text="앞서 1.2절에서 배운 군을 떠올려보세요."):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": text}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_backward_link_returns_latex_block(self):
        """generate_backward_link returns a linkbox LaTeX block."""
        with patch("requests.post", return_value=self._mock_llm()):
            result = self.analyzer.generate_backward_link("2.1")
        self.assertIn("\\begin{linkbox}", result)
        self.assertIn("\\end{linkbox}", result)

    def test_forward_link_returns_latex_block(self):
        """generate_forward_link returns a previewbox LaTeX block."""
        with patch("requests.post", return_value=self._mock_llm("여기서 배운 군은 2.1절에서 핵심입니다.")):
            result = self.analyzer.generate_forward_link("1.2")
        self.assertIn("\\begin{previewbox}", result)
        self.assertIn("\\end{previewbox}", result)

    def test_no_backward_link_for_first_section(self):
        """First section has no backward references → empty string."""
        result = self.analyzer.generate_backward_link("1.2")
        self.assertEqual(result, "")

    def test_no_forward_link_for_last_section(self):
        """Last section has no forward references → empty string."""
        result = self.analyzer.generate_forward_link("2.1")
        self.assertEqual(result, "")

    def test_get_all_links_returns_tuple(self):
        """get_all_links returns (backward_str, forward_str) tuple."""
        with patch("requests.post", return_value=self._mock_llm()):
            backward, forward = self.analyzer.get_all_links("2.1")
        self.assertIsInstance(backward, str)
        self.assertIsInstance(forward, str)

    def test_fallback_used_when_llm_fails(self):
        """When LLM fails, fallback template is used (non-empty result)."""
        with patch("requests.post", side_effect=Exception("LLM down")):
            result = self.analyzer.generate_backward_link("2.1")
        # Should still produce a linkbox using the fallback template
        self.assertIn("\\begin{linkbox}", result)
        self.assertIn("1.2", result)

    def test_latex_preamble_contains_both_boxes(self):
        """Static latex_preamble() includes both linkbox and previewbox."""
        preamble = LinkageAnalyzer.latex_preamble()
        self.assertIn("linkbox", preamble)
        self.assertIn("previewbox", preamble)


# ============================================================
# Issue #9 — CompanionExplainer
# ============================================================

class TestCompanionExplainerGate(unittest.TestCase):
    """Tests for the gate logic (should_explain)."""

    def setUp(self):
        self.explainer = CompanionExplainer(threshold=0.4, max_per_page=2)

    def test_gate_passes_high_abstraction(self):
        """High abstraction + LaTeX → should_explain = True."""
        text = "임의의 $\\epsilon > 0$에 대해 $\\delta > 0$가 존재하여 $|f(x) - L| < \\epsilon$"
        self.assertTrue(self.explainer.should_explain(text, 0.8, 0))

    def test_gate_fails_low_abstraction(self):
        """Low abstraction → should_explain = False."""
        text = "임의의 $\\epsilon > 0$에 대해 $\\delta > 0$가 존재합니다."
        self.assertFalse(self.explainer.should_explain(text, 0.2, 0))

    def test_gate_fails_when_page_count_exceeded(self):
        """Already at max_per_page → should_explain = False."""
        text = "임의의 $\\epsilon > 0$에 대해 $\\delta > 0$가 존재합니다."
        self.assertFalse(self.explainer.should_explain(text, 0.8, 2))

    def test_gate_fails_no_latex(self):
        """Text with no LaTeX formulas → should_explain = False."""
        text = "이 개념은 매우 중요합니다. 수학에서 핵심 역할을 합니다."
        self.assertFalse(self.explainer.should_explain(text, 0.9, 0))

    def test_gate_passes_exactly_at_threshold(self):
        """abstraction_score exactly at threshold → True (boundary)."""
        text = "임의의 $\\epsilon > 0$에 대해 $\\delta > 0$가 존재합니다."
        self.assertTrue(self.explainer.should_explain(text, 0.4, 0))

    def test_gate_fails_just_below_threshold(self):
        """abstraction_score just below threshold → False."""
        text = "임의의 $\\epsilon > 0$에 대해 $\\delta > 0$가 존재합니다."
        self.assertFalse(self.explainer.should_explain(text, 0.39, 0))


class TestCompanionExplainerLatexCount(unittest.TestCase):
    """Tests for _count_latex helper."""

    def test_inline_formulas_counted(self):
        """Inline $...$ formulas are counted."""
        text = "함수 $f(x)$와 $g(x)$는 연속입니다."
        count = CompanionExplainer._count_latex(text)
        self.assertEqual(count, 2)

    def test_display_formulas_counted(self):
        """Display $$...$$ formulas are counted."""
        text = "$$\\int_0^1 f(x) dx = F(1) - F(0)$$"
        count = CompanionExplainer._count_latex(text)
        self.assertEqual(count, 1)

    def test_equation_environment_counted(self):
        """\\begin{equation} environments are counted."""
        text = "\\begin{equation} E = mc^2 \\end{equation}"
        count = CompanionExplainer._count_latex(text)
        self.assertGreaterEqual(count, 1)

    def test_no_latex_returns_zero(self):
        """Plain text with no LaTeX returns 0."""
        text = "이 개념은 중요합니다."
        self.assertEqual(CompanionExplainer._count_latex(text), 0)


class TestCompanionExplainerGeneration(unittest.TestCase):
    """Tests for LLM generation and injection."""

    def setUp(self):
        self.explainer = CompanionExplainer(threshold=0.4, max_per_page=2)

    def _mock_llm(self, text="쉽게 말하면, 함수가 연속이라는 것은 그래프를 그릴 때 손을 떼지 않아도 된다는 뜻입니다."):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": text}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_inject_adds_plainexplain_block(self):
        """inject() wraps plain text in plainexplain environment."""
        result = self.explainer.inject("formal text", "plain text")
        self.assertIn("\\begin{plainexplain}", result)
        self.assertIn("\\end{plainexplain}", result)
        self.assertIn("plain text", result)
        self.assertIn("formal text", result)

    def test_inject_unchanged_when_empty_plain(self):
        """inject() returns formal_text unchanged when plain_text is empty."""
        result = self.explainer.inject("formal text", "")
        self.assertEqual(result, "formal text")

    def test_generate_plain_returns_string(self):
        """generate_plain returns a non-empty string on success."""
        with patch("requests.post", return_value=self._mock_llm()):
            result = self.explainer.generate_plain("$\\epsilon$-$\\delta$ 정의...", "analysis")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_generate_plain_returns_empty_on_failure(self):
        """generate_plain returns empty string when LLM is unavailable."""
        with patch("requests.post", side_effect=Exception("connection failed")):
            result = self.explainer.generate_plain("some formal text", "algebra")
        self.assertEqual(result, "")

    def test_process_returns_explanation_result(self):
        """process() returns ExplanationResult with output field."""
        formal = "임의의 $\\epsilon > 0$에 대해 $\\delta > 0$가 존재합니다."
        with patch("requests.post", return_value=self._mock_llm()):
            result = self.explainer.process(formal, 0.7, "analysis", 0)
        self.assertIsInstance(result, ExplanationResult)
        self.assertEqual(result.formal_text, formal)
        self.assertIsInstance(result.output, str)

    def test_process_skips_below_threshold(self):
        """process() skips generation when abstraction_score < threshold."""
        formal = "임의의 $\\epsilon > 0$에 대해 $\\delta > 0$가 존재합니다."
        result = self.explainer.process(formal, 0.1, "analysis", 0)
        self.assertFalse(result.added)
        self.assertEqual(result.output, formal)
        self.assertEqual(result.plain_text, "")

    def test_process_respects_max_per_page(self):
        """process() skips when page_explanation_count >= max_per_page."""
        formal = "임의의 $\\epsilon > 0$에 대해 $\\delta > 0$가 존재합니다."
        result = self.explainer.process(formal, 0.9, "analysis", page_explanation_count=2)
        self.assertFalse(result.added)
        self.assertEqual(result.output, formal)

    def test_process_added_false_when_llm_fails(self):
        """process() sets added=False when LLM returns empty string."""
        formal = "임의의 $\\epsilon > 0$에 대해 $\\delta > 0$가 존재합니다."
        with patch("requests.post", side_effect=Exception("LLM down")):
            result = self.explainer.process(formal, 0.9, "analysis", 0)
        self.assertFalse(result.added)
        self.assertEqual(result.output, formal)

    def test_latex_preamble_contains_plainexplain(self):
        """Static latex_preamble() includes plainexplain definition."""
        preamble = CompanionExplainer.latex_preamble()
        self.assertIn("plainexplain", preamble)
        self.assertIn("newtcolorbox", preamble)


# ============================================================
# Integration: all three modules together
# ============================================================

class TestIntegrationFlow(unittest.TestCase):
    """
    Smoke test: MotivationAgent generates analogy →
    AnalogyVerifier validates → CompanionExplainer adds plain note.
    """

    def _mock_llm_score_85(self, *args, **kwargs):
        resp = MagicMock()
        resp.json.return_value = {"response": "SCORE: 85\nREASON: 수학적으로 적절함"}
        resp.raise_for_status = MagicMock()
        return resp

    def _mock_llm_plain(self, *args, **kwargs):
        resp = MagicMock()
        resp.json.return_value = {"response": "쉽게 말하면 이 개념은 X와 Y를 연결합니다."}
        resp.raise_for_status = MagicMock()
        return resp

    def test_full_pipeline_produces_output(self):
        """Full pipeline: verify analogy → add companion → produce LaTeX output."""
        analogy = "군은 마치 대칭성의 추상화입니다."
        formal = "군 $G$는 결합법칙, 항등원, 역원을 가진 집합입니다. $a \\cdot e = a$"

        verifier = AnalogyVerifier()
        explainer = CompanionExplainer(threshold=0.3)

        with patch("requests.post", side_effect=self._mock_llm_score_85):
            ver_result = verifier.verify(analogy, formal, "algebra")

        self.assertTrue(ver_result.passed)

        with patch("requests.post", side_effect=self._mock_llm_plain):
            exp_result = explainer.process(formal, 0.7, "algebra", 0)

        self.assertIn("plainexplain", exp_result.output)

    def test_linkage_and_companion_independent(self):
        """LinkageAnalyzer and CompanionExplainer can be used independently."""
        analyzer = LinkageAnalyzer()
        sections = [
            SectionInfo(id="1.1", title="집합", key_concepts=["집합", "원소"]),
            SectionInfo(id="1.2", title="함수", key_concepts=["함수", "집합", "정의역"]),
        ]
        analyzer.build_reference_map(sections)

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                json=MagicMock(return_value={"response": "앞서 1.1절에서 배운 집합을 기반으로 함수를 정의합니다."}),
                raise_for_status=MagicMock()
            )
            backward = analyzer.generate_backward_link("1.2")

        self.assertIn("linkbox", backward)


if __name__ == "__main__":
    unittest.main()
