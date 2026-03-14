"""
Five pipeline stage implementations for the MasterPipeline.

Each stage:
  - Accepts sections_text: list of {"section_id": str, "text": str}
  - Returns: {"sections": [...processed...], "summary": {...}}
  - Never raises — catches exceptions, logs them, marks section as "failed"
"""

from __future__ import annotations

import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

import requests

from src.pcm.core.llm_client import OllamaClient, _DEFAULT_BASE_URL, _DEFAULT_MODEL

if TYPE_CHECKING:
    from src.pcm.pipeline.db import PipelineDB
    from src.pcm.pipeline.logger import PipelineLogger


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseStage:
    stage_num: int
    stage_name: str

    def run(
        self,
        job: dict,
        stage: dict,
        sections_text: list[dict],
        db: "PipelineDB",
        logger: "PipelineLogger",
    ) -> dict:
        """
        sections_text: list of {"section_id": str, "text": str}
        Returns: {"sections": [...processed...], "summary": {...}}
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Stage 1 — Domain Orientation
# ---------------------------------------------------------------------------

class Stage1_Orientation(BaseStage):
    stage_num = 1
    stage_name = "Domain Orientation"

    def run(self, job, stage, sections_text, db, logger):
        from src.pcm.core.wsd_agent import DomainClassifier
        from src.pcm.core.knowledge_manager import KnowledgeManager

        classifier = DomainClassifier()
        km = KnowledgeManager()

        processed = []
        domains_found: dict[str, int] = {}
        wsd_failures = 0

        logger.info(
            f"Stage 1 starting: {len(sections_text)} sections",
            details={"section_count": len(sections_text)},
        )

        # Layout parser — used when sections arrive without block metadata
        try:
            from src.pcm.core.layout_parser import LayoutAwareParser
            layout_parser = LayoutAwareParser()
        except Exception:
            layout_parser = None

        for sec in sections_text:
            sec_id = sec["section_id"]
            text = sec.get("text", "")
            sec_logger = logger.bind(section_id=sec_id, agent_name="WSDAgent")

            db_sec_id = db.create_section(
                job_id=job["id"],
                stage_id=stage["id"],
                section_id=sec_id,
                original_en=text,
            )
            db.update_section(db_sec_id, status="running")

            # Attach block metadata when only raw text is available
            if "block_type" not in sec and layout_parser is not None:
                try:
                    parsed_blocks = layout_parser.parse_text(text, page=0)
                    sec["block_type"] = parsed_blocks[0].block_type if parsed_blocks else "body"
                    sec["blocks_metadata"] = layout_parser.to_json(parsed_blocks)
                except Exception as exc:
                    sec_logger.warning(
                        f"LayoutAwareParser failed for section {sec_id}: {exc} — using defaults",
                        details={"traceback": traceback.format_exc()},
                    )
                    sec.setdefault("block_type", "body")
                    sec.setdefault("blocks_metadata", {})
            # Compute abstraction_score from LaTeX density + math term frequency
            if "abstraction_score" not in sec:
                try:
                    from src.pcm.core.semantic_chunker import SemanticChunker
                    sec["abstraction_score"] = SemanticChunker()._compute_abstraction_score(text)
                except Exception as exc:
                    sec_logger.warning(
                        f"abstraction_score failed for section {sec_id}: {exc} — defaulting to 0.0",
                    )
                    sec["abstraction_score"] = 0.0

            try:
                domain = classifier.classify(text)
                terminology_guide = km.inject_to_prompt(domain)

                domains_found[domain] = domains_found.get(domain, 0) + 1

                db.update_section(
                    db_sec_id,
                    wsd_domain=domain,
                    status="completed",
                )

                sec_logger.info(
                    f"Section {sec_id} classified as '{domain}'",
                    details={"domain": domain},
                )

                processed.append({
                    "section_id": sec_id,
                    "text": text,
                    "domain": domain,
                    "terminology_guide": terminology_guide,
                    "db_section_id": db_sec_id,
                    "block_type": sec.get("block_type", "body"),
                    "blocks_metadata": sec.get("blocks_metadata", {}),
                    "abstraction_score": sec.get("abstraction_score", 0.0),
                })

            except Exception as exc:
                wsd_failures += 1
                sec_logger.error(
                    f"WSD failed for section {sec_id}: {exc}",
                    details={"traceback": traceback.format_exc()},
                )
                db.update_section(db_sec_id, status="failed")
                # Carry forward with "general" domain so later stages still work
                processed.append({
                    "section_id": sec_id,
                    "text": text,
                    "domain": "general",
                    "terminology_guide": "",
                    "db_section_id": db_sec_id,
                    "block_type": sec.get("block_type", "body"),
                    "blocks_metadata": sec.get("blocks_metadata", {}),
                    "abstraction_score": sec.get("abstraction_score", 0.0),
                })

        stats = km.get_stats()
        logger.info(
            "Stage 1 complete",
            details={
                "section_count": len(sections_text),
                "domains_found": domains_found,
                "wsd_failures": wsd_failures,
                "knowledge_stats": stats,
            },
        )

        return {
            "sections": processed,
            "summary": {
                "section_count": len(processed),
                "domains_found": domains_found,
                "wsd_failures": wsd_failures,
            },
        }


# ---------------------------------------------------------------------------
# Stage 2 — Initial Draft
# ---------------------------------------------------------------------------

class Stage2_Drafting(BaseStage):
    stage_num = 2
    stage_name = "Initial Draft"

    MAX_WORKERS = 4   # parallel section translation threads

    # Domain → (system_role, translate_instruction)
    _DOMAIN_PROMPTS: dict[str, tuple[str, str]] = {
        "machine_learning": (
            "당신은 AI/머신러닝 분야 전문 번역가입니다. "
            "기술 용어는 정확하게 번역하고, 원문의 학술 문체를 유지하세요.",
            "다음 영어 AI/머신러닝 텍스트를 한국어로 번역하세요",
        ),
        "computer_science": (
            "당신은 컴퓨터 과학 분야 전문 번역가입니다. "
            "기술 용어는 정확하게 번역하고, 원문의 학술 문체를 유지하세요.",
            "다음 영어 컴퓨터 과학 텍스트를 한국어로 번역하세요",
        ),
        "nlp": (
            "당신은 자연어 처리(NLP) 분야 전문 번역가입니다. "
            "기술 용어는 정확하게 번역하고, 원문의 학술 문체를 유지하세요.",
            "다음 영어 NLP 텍스트를 한국어로 번역하세요",
        ),
    }

    _MATH_SYSTEM = (
        "당신은 수학/물리 전문 번역가입니다. "
        "수식($...$)은 절대 변형하지 마세요. "
        "주어진 용어 사전을 반드시 따르세요."
    )
    _MATH_INSTRUCTION = "다음 영어 수학/물리 텍스트를 한국어로 번역하세요"

    _GENERAL_SYSTEM = (
        "당신은 학술 문서 전문 번역가입니다. "
        "원문의 의미와 학술 문체를 정확히 유지하며 한국어로 번역하세요."
    )
    _GENERAL_INSTRUCTION = "다음 영어 학술 텍스트를 한국어로 번역하세요"

    def __init__(self):
        self._llm = OllamaClient()

    def _get_domain_prompt(self, domain: str) -> tuple[str, str]:
        """Return (system_role, instruction) for the given domain."""
        if domain in self._DOMAIN_PROMPTS:
            return self._DOMAIN_PROMPTS[domain]
        if domain == "general":
            return self._GENERAL_SYSTEM, self._GENERAL_INSTRUCTION
        return self._MATH_SYSTEM, self._MATH_INSTRUCTION

    # Appended to every prompt — prevents Chinese/English fallback in qwen2.5
    _KOREAN_ONLY = (
        "\n\n[필수 규칙] 반드시 한국어(Korean)로만 번역하세요. "
        "절대 중국어(Chinese)나 영어(English)로 번역하지 마세요. "
        "번역 외 설명이나 머리말은 쓰지 마세요. "
        "번역 결과만 출력하세요."
    )

    def _translate(self, text: str, terminology_guide: str, domain: str = "general") -> str:
        system_role, instruction = self._get_domain_prompt(domain)
        full_prompt = (
            f"{system_role}{self._KOREAN_ONLY}\n\n"
            f"{terminology_guide}\n\n"
            f"{instruction}:\n\n{text}"
        )
        result = self._llm.generate(full_prompt, temperature=0.2, timeout=60)
        # Post-check: reject if non-Korean (Chinese CJK or mostly English)
        return self._enforce_korean(result, text)

    @staticmethod
    def _enforce_korean(result: str, original: str) -> str:
        """Return cleaned text or empty string if result is clearly not Korean."""
        import re as _re
        if not result:
            return ""
        # Strip trailing Chinese characters (common LLM bleed-through at end of output)
        result = _re.sub(r"[\u4E00-\u9FFF\uF900-\uFAFF]+\s*$", "", result).rstrip()
        # Count Korean, Chinese, and total alpha chars
        korean = sum(1 for c in result if "\uAC00" <= c <= "\uD7A3")
        chinese = sum(1 for c in result if "\u4E00" <= c <= "\u9FFF")
        alpha = sum(1 for c in result if c.isalpha())
        if alpha == 0:
            return result
        # If Chinese chars dominate (> 20%) → not Korean output
        if chinese / alpha > 0.2:
            return ""
        # If Korean chars are < 10% of alpha and result is long → not translated
        if korean / alpha < 0.10 and len(result.split()) > 20:
            return ""
        return result

    def _process_section(self, sec: dict, job: dict, db, logger) -> dict:
        """Translate a single section. Returns the updated section dict."""
        sec_id = sec["section_id"]
        text = sec.get("text", "")
        domain = sec.get("domain", "general")
        terminology_guide = sec.get("terminology_guide", "")
        db_sec_id = sec.get("db_section_id") or f"{job['id']}_{sec_id}"

        sec_logger = logger.bind(section_id=db_sec_id, agent_name="InitialTranslator")
        db.update_section(db_sec_id, status="running")

        t_start = time.time()
        try:
            draft_ko = self._translate(text, terminology_guide, domain)
            if not draft_ko:
                raise ValueError("LLM returned empty translation")
            elapsed = round(time.time() - t_start, 2)

            db.add_iteration(
                section_id=db_sec_id,
                job_id=job["id"],
                iteration_num=0,
                agent_name="InitialTranslator",
                translated_text=draft_ko,
                score=None,
                critique=None,
            )
            db.update_section(db_sec_id, final_ko=draft_ko, status="completed")
            sec_logger.info(
                f"Section {sec_id} drafted in {elapsed}s",
                details={"elapsed_s": elapsed, "domain": domain},
            )
            return {**sec, "draft_ko": draft_ko, "db_section_id": db_sec_id}

        except Exception as exc:
            elapsed = round(time.time() - t_start, 2)
            sec_logger.error(
                f"Draft failed for section {sec_id}: {exc}",
                details={"traceback": traceback.format_exc(), "elapsed_s": elapsed},
            )
            db.update_section(db_sec_id, final_ko=text, status="failed")
            return {**sec, "draft_ko": text, "db_section_id": db_sec_id}

    def run(self, job, stage, sections_text, db, logger):
        logger.info(
            f"Stage 2 starting: {len(sections_text)} sections "
            f"(max_workers={self.MAX_WORKERS})",
            details={"section_count": len(sections_text), "max_workers": self.MAX_WORKERS},
        )

        # Preserve original section order after parallel execution
        ordered: dict[str, dict] = {}

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._process_section, sec, job, db, logger): sec["section_id"]
                for sec in sections_text
            }
            for future in as_completed(futures):
                result = future.result()
                ordered[result["section_id"]] = result

        # Restore input order
        processed = [ordered[sec["section_id"]] for sec in sections_text]

        logger.info(
            "Stage 2 complete",
            details={"section_count": len(processed)},
        )
        return {
            "sections": processed,
            "summary": {"section_count": len(processed)},
        }


# ---------------------------------------------------------------------------
# Stage 3 — TCR Refinement
# ---------------------------------------------------------------------------

class Stage3_Refinement(BaseStage):
    stage_num = 3
    stage_name = "TCR Refinement"

    MAX_ITERATIONS = 3
    THRESHOLD = 80

    def run(self, job, stage, sections_text, db, logger):
        from src.pcm.core.tcr_loop import TCRLoop
        from src.pcm.core.knowledge_manager import KnowledgeManager
        from src.pcm.core.fluency_agent import FluencyAgent
        from src.pcm.core.naturalness_editor import NaturalnessEditor

        km = KnowledgeManager()
        tcr = TCRLoop(
            model=_DEFAULT_MODEL,
            threshold=self.THRESHOLD,
            max_iterations=self.MAX_ITERATIONS,
        )
        fluency_agent = FluencyAgent()
        naturalness_editor = NaturalnessEditor()

        processed = []

        logger.info(
            f"Stage 3 starting: {len(sections_text)} sections "
            f"(TCR + FluencyAgent + NaturalnessEditor)",
            details={"section_count": len(sections_text)},
        )

        for sec in sections_text:
            sec_id = sec["section_id"]
            text = sec.get("text", "")
            domain = sec.get("domain", "general")
            draft_ko = sec.get("draft_ko", text)
            terminology_guide = sec.get("terminology_guide", "")
            db_sec_id = sec.get("db_section_id") or f"{job['id']}_{sec_id}"

            sec_logger = logger.bind(section_id=db_sec_id, agent_name="Stage3")
            db.update_section(db_sec_id, status="running")

            try:
                glossary = km.get_all_for_domain(domain)

                # Domain-aware initial prompt
                domain_role = {
                    "machine_learning": "AI/머신러닝 분야 전문 번역가",
                    "computer_science": "컴퓨터 과학 분야 전문 번역가",
                    "nlp": "자연어 처리(NLP) 분야 전문 번역가",
                }.get(domain, "학술 문서 전문 번역가")

                feedback_context = ""
                try:
                    from src.pcm.core.feedback_loop import FeedbackInjector, FeedbackDB
                    feedback_context = FeedbackInjector(FeedbackDB()).inject_to_translator_prompt(sec_id, top_k=3)
                except Exception:
                    pass

                initial_prompt = (
                    f"당신은 {domain_role}입니다. "
                    "반드시 한국어로만 번역하세요. 중국어·영어로 번역하지 마세요. "
                    "수식($...$)은 절대 변형하지 마세요. 학술 격식체를 사용하세요.\n\n"
                    f"{terminology_guide}\n\n{feedback_context}"
                )

                # ── TCR loop ───────────────────────────────────────────────
                final_ko, trace = tcr.run(
                    original_en=text,
                    glossary=glossary,
                    initial_prompt=initial_prompt,
                )

                iterations = trace.get("iterations", [])
                for it in iterations:
                    db.add_iteration(
                        section_id=db_sec_id,
                        job_id=job["id"],
                        iteration_num=it["iteration"],
                        agent_name="TCRRefiner",
                        translated_text=it.get("translated"),
                        score=it.get("score"),
                        critique=it.get("critique"),
                    )

                # ── FluencyAgent: proper multi-dimensional score ──────────
                fluency = fluency_agent.score(text, final_ko, glossary)
                final_score = fluency.total
                score_trajectory = "→".join(
                    str(it.get("score", 0)) for it in iterations
                ) + f"→F{final_score}"

                sec_logger.info(
                    f"Section {sec_id}: fluency={final_score} "
                    f"(acc={fluency.accuracy} flu={fluency.fluency} "
                    f"tone={fluency.tone} term={fluency.terminology})",
                    details={
                        "fluency_score": final_score,
                        "language_ok": fluency.language_ok,
                        "critique": fluency.critique,
                    },
                )

                # ── NaturalnessEditor: fix awkward patterns ───────────────
                edit_result = naturalness_editor.edit(final_ko, text)
                if edit_result.changed:
                    final_ko = edit_result.edited
                    sec_logger.info(
                        f"Section {sec_id}: naturalness fixes: {edit_result.issues_found}",
                    )

                db.update_section(
                    db_sec_id,
                    final_ko=final_ko,
                    final_score=final_score,
                    status="completed",
                )

                processed.append({
                    **sec,
                    "final_ko": final_ko,
                    "final_score": final_score,
                    "score_trajectory": score_trajectory,
                    "fluency_detail": {
                        "accuracy": fluency.accuracy,
                        "fluency": fluency.fluency,
                        "tone": fluency.tone,
                        "terminology": fluency.terminology,
                        "critique": fluency.critique,
                        "language_ok": fluency.language_ok,
                    },
                    "naturalness_fixes": edit_result.issues_found,
                    "db_section_id": db_sec_id,
                })

            except Exception as exc:
                sec_logger.error(
                    f"Stage3 failed for section {sec_id}: {exc}",
                    details={"traceback": traceback.format_exc()},
                )
                db.update_section(db_sec_id, final_ko=draft_ko, status="failed")
                processed.append({
                    **sec,
                    "final_ko": draft_ko,
                    "final_score": 0.0,
                    "score_trajectory": "0",
                    "db_section_id": db_sec_id,
                })

        logger.info(
            "Stage 3 complete",
            details={"section_count": len(processed)},
        )

        return {
            "sections": processed,
            "summary": {"section_count": len(processed)},
        }


# ---------------------------------------------------------------------------
# Stage 4 — Consistency Validation
# ---------------------------------------------------------------------------

class Stage4_Validation(BaseStage):
    stage_num = 4
    stage_name = "Consistency Validation"

    def _dominant_domain(self, sections: list[dict]) -> str:
        counts: dict[str, int] = {}
        for s in sections:
            d = s.get("domain", "general")
            counts[d] = counts.get(d, 0) + 1
        if not counts:
            return "general"
        return max(counts, key=counts.get)

    def run(self, job, stage, sections_text, db, logger):
        from src.pcm.core.consistency_manager import ConsistencyManager
        from src.pcm.core.knowledge_manager import KnowledgeManager
        from src.pcm.core.back_translation_verifier import BackTranslationVerifier

        km = KnowledgeManager()
        cm = ConsistencyManager()
        bt_verifier = BackTranslationVerifier()

        dominant = self._dominant_domain(sections_text)
        glossary = km.get_all_for_domain(dominant)

        total_inconsistencies = 0
        fixed_count = 0
        bt_failed = 0
        processed = []

        logger.info(
            f"Stage 4 starting: dominant_domain={dominant}, "
            f"{len(sections_text)} sections (+ BackTranslationVerifier)",
            details={"dominant_domain": dominant, "section_count": len(sections_text)},
        )

        for sec in sections_text:
            sec_id = sec["section_id"]
            text = sec.get("text", "")
            final_ko = sec.get("final_ko", sec.get("draft_ko", text))
            db_sec_id = sec.get("db_section_id") or f"{job['id']}_{sec_id}"

            sec_logger = logger.bind(
                section_id=db_sec_id, agent_name="ConsistencyManager"
            )
            db.update_section(db_sec_id, status="running")

            try:
                # Build translation memory from glossary
                cm.update_memory(text, final_ko, glossary)

                # Check for inconsistencies by scanning consistency prompt
                consistency_prompt = cm.get_consistency_prompt()

                # Detect simple term inconsistencies: glossary terms found in
                # original but NOT correctly translated in final_ko
                section_inconsistencies = []
                for en_term, ko_term in glossary.items():
                    if (
                        en_term.lower() in text.lower()
                        and ko_term
                        and ko_term not in final_ko
                    ):
                        section_inconsistencies.append(
                            {"term": en_term, "expected": ko_term}
                        )

                if section_inconsistencies:
                    total_inconsistencies += len(section_inconsistencies)
                    sec_logger.warning(
                        f"Section {sec_id}: {len(section_inconsistencies)} inconsistencies",
                        details={"inconsistencies": section_inconsistencies},
                    )

                    # Apply fixes: append a correction note to the translation
                    # (full re-translation is done by Stage 3; here we note them)
                    fix_note = "\n".join(
                        f"[{item['term']} → {item['expected']}]"
                        for item in section_inconsistencies
                    )
                    fixed_ko = final_ko + "\n\n<!-- consistency fixes: " + fix_note + " -->"
                    fixed_count += len(section_inconsistencies)
                else:
                    fixed_ko = final_ko
                    sec_logger.info(
                        f"Section {sec_id}: no inconsistencies found"
                    )

                # ── BackTranslationVerifier ──────────────────────────────
                bt_result = None
                try:
                    bt_result = bt_verifier.verify(text, fixed_ko)
                    if not bt_result.passed:
                        bt_failed += 1
                        sec_logger.warning(
                            f"Section {sec_id}: back-translation similarity={bt_result.similarity:.2f} "
                            f"< threshold — drift terms: {bt_result.drift_terms}",
                            details={
                                "bt_similarity": bt_result.similarity,
                                "bt_method": bt_result.method,
                                "drift_terms": bt_result.drift_terms,
                                "back_translation": bt_result.back_translation[:200],
                            },
                        )
                    else:
                        sec_logger.info(
                            f"Section {sec_id}: back-translation OK "
                            f"(similarity={bt_result.similarity:.2f}, method={bt_result.method})"
                        )
                except Exception as bt_exc:
                    sec_logger.warning(f"BackTranslation skipped: {bt_exc}")

                db.update_section(
                    db_sec_id,
                    final_ko=fixed_ko,
                    status="completed",
                )

                processed.append({
                    **sec,
                    "final_ko": fixed_ko,
                    "db_section_id": db_sec_id,
                    "bt_similarity": bt_result.similarity if bt_result else None,
                    "bt_passed": bt_result.passed if bt_result else None,
                    "bt_drift_terms": bt_result.drift_terms if bt_result else [],
                })

            except Exception as exc:
                sec_logger.error(
                    f"Consistency check failed for section {sec_id}: {exc}",
                    details={"traceback": traceback.format_exc()},
                )
                db.update_section(db_sec_id, status="failed")
                processed.append({**sec, "db_section_id": db_sec_id})

        # ── Cross-Reference Narrative ──────────────────────────────────────
        # Build a reference map across all sections and inject backward/forward
        # link boxes into the translated text.
        cross_ref_count = 0
        try:
            from src.pcm.core.cross_reference import LinkageAnalyzer, SectionInfo, extract_concepts_from_text

            link_analyzer = LinkageAnalyzer()
            sec_infos = []
            for sec in processed:
                concepts = extract_concepts_from_text(sec.get("final_ko", ""))
                sec_infos.append(SectionInfo(
                    id=sec["section_id"],
                    title=sec["section_id"],
                    key_concepts=concepts,
                    text_snippet=sec.get("final_ko", "")[:300],
                ))
            link_analyzer.build_reference_map(sec_infos)

            for sec in processed:
                backward, forward = link_analyzer.get_all_links(sec["section_id"])
                if backward or forward:
                    cross_ref_count += 1
                    sec["final_ko"] = backward + sec.get("final_ko", "") + "\n\n" + forward
                    sec["cross_ref_injected"] = True
                else:
                    sec["cross_ref_injected"] = False

            logger.info(
                f"Cross-reference links injected for {cross_ref_count} sections",
                details={"cross_ref_count": cross_ref_count},
            )
        except Exception as exc:
            logger.warning(
                f"CrossReference failed (non-fatal): {exc}",
                details={"traceback": traceback.format_exc()},
            )

        logger.info(
            "Stage 4 complete",
            details={
                "total_inconsistencies": total_inconsistencies,
                "fixed_count": fixed_count,
                "cross_ref_count": cross_ref_count,
            },
        )

        return {
            "sections": processed,
            "summary": {
                "section_count": len(processed),
                "total_inconsistencies": total_inconsistencies,
                "fixed_count": fixed_count,
                "cross_ref_count": cross_ref_count,
            },
        }


# ---------------------------------------------------------------------------
# Stage 5 — Typesetting & Evolution
# ---------------------------------------------------------------------------

class Stage5_Evolution(BaseStage):
    stage_num = 5
    stage_name = "Typesetting & Evolution"

    def run(self, job, stage, sections_text, db, logger):
        from src.pcm.core.feedback_loop import FeedbackInjector, FeedbackDB

        feedback_db = FeedbackDB()
        injector = FeedbackInjector(db=feedback_db)

        # MotivationAgent — loaded once, used per-section
        try:
            from src.pcm.core.motivation_agent import MotivationAgent
            motivation_agent = MotivationAgent()
        except Exception as exc:
            logger.warning(f"MotivationAgent unavailable: {exc}")
            motivation_agent = None

        # AnalogyVerifier — validates motivation blocks before injection
        try:
            from src.pcm.core.analogy_verifier import AnalogyVerifier
            analogy_verifier = AnalogyVerifier()
        except Exception as exc:
            logger.warning(f"AnalogyVerifier unavailable: {exc}")
            analogy_verifier = None

        # CompanionExplainer — plain language side notes
        try:
            from src.pcm.core.companion_explainer import CompanionExplainer
            companion_explainer = CompanionExplainer(threshold=0.5, max_per_page=2)
        except Exception as exc:
            logger.warning(f"CompanionExplainer unavailable: {exc}")
            companion_explainer = None

        # Track companion count per "page" (approximate: every 3 sections = 1 page)
        page_companion_count: dict[int, int] = {}

        output_sections = []
        scores = []
        processed = []

        logger.info(
            f"Stage 5 starting: {len(sections_text)} sections",
            details={"section_count": len(sections_text)},
        )

        for sec in sections_text:
            sec_id = sec["section_id"]
            text = sec.get("text", "")
            final_ko = sec.get("final_ko", sec.get("draft_ko", text))
            final_score = sec.get("final_score", 0.0)
            domain = sec.get("domain", "general")
            db_sec_id = sec.get("db_section_id") or f"{job['id']}_{sec_id}"

            sec_logger = logger.bind(
                section_id=db_sec_id, agent_name="FeedbackInjector"
            )
            db.update_section(db_sec_id, status="running")

            try:
                few_shot_ctx = injector.inject_to_translator_prompt(
                    section_id=sec_id, top_k=5
                )

                # MotivationAgent: inject motivation block for high-abstraction sections
                motivation_injected = False
                if motivation_agent is not None:
                    block_type = sec.get("block_type", "body")
                    abstraction_score = sec.get("abstraction_score", 0.0)
                    if motivation_agent.should_generate(block_type, abstraction_score):
                        try:
                            motivation = motivation_agent.generate(
                                unit_text=text,
                                domain=domain,
                                section_title=sec_id,
                            )
                            if motivation:
                                # AnalogyVerifier: validate before injecting
                                verified_motivation = motivation
                                if analogy_verifier is not None:
                                    ver_result = analogy_verifier.verify(
                                        analogy_text=motivation,
                                        formal_definition=text[:300],
                                        domain=domain,
                                    )
                                    if ver_result.level == "FAIL":
                                        sec_logger.warning(
                                            f"Section {sec_id}: analogy FAILED verification "
                                            f"({ver_result.reason[:80]}), skipping injection",
                                        )
                                        verified_motivation = ""
                                    else:
                                        verified_motivation = ver_result.analogy
                                        if ver_result.level == "WARN":
                                            sec_logger.info(
                                                f"Section {sec_id}: analogy WARN — "
                                                f"scope limiter added (score={ver_result.score})",
                                            )

                                if verified_motivation:
                                    final_ko = motivation_agent.inject_into_translation(
                                        final_ko, verified_motivation
                                    )
                                    motivation_injected = True
                                    sec_logger.info(
                                        f"Section {sec_id}: motivation block injected "
                                        f"(block_type={block_type}, "
                                        f"abstraction={abstraction_score:.2f})",
                                        details={
                                            "block_type": block_type,
                                            "abstraction_score": abstraction_score,
                                        },
                                    )
                        except Exception:
                            pass

                # CompanionExplainer: plain language note for formal math blocks
                companion_injected = False
                if companion_explainer is not None:
                    try:
                        page_num = len(output_sections) // 3
                        page_count = page_companion_count.get(page_num, 0)
                        abstraction_score = sec.get("abstraction_score", 0.0)
                        # Use original English for LaTeX density check (PDF text may lack $)
                        check_text = text if companion_explainer._count_latex(final_ko) == 0 else final_ko
                        exp_result = companion_explainer.process(
                            formal_text=final_ko,
                            abstraction_score=abstraction_score,
                            domain=domain,
                            page_explanation_count=page_count,
                        )
                        # Override gate: also fire when original has LaTeX + high abstraction
                        if not exp_result.added and abstraction_score >= companion_explainer.threshold:
                            if companion_explainer._count_latex(check_text) >= 1 and page_count < companion_explainer.max_per_page:
                                plain = companion_explainer.generate_plain(final_ko, domain)
                                if plain:
                                    from src.pcm.core.companion_explainer import ExplanationResult
                                    exp_result = ExplanationResult(
                                        formal_text=final_ko,
                                        plain_text=plain,
                                        added=True,
                                        output=companion_explainer.inject(final_ko, plain),
                                    )
                        if exp_result.added:
                            final_ko = exp_result.output
                            companion_injected = True
                            page_companion_count[page_num] = page_count + 1
                            sec_logger.info(
                                f"Section {sec_id}: companion explanation injected "
                                f"(abstraction={abstraction_score:.2f})",
                            )
                    except Exception:
                        pass

                if final_score:
                    scores.append(final_score)

                output_sections.append({
                    "section_id": sec_id,
                    "original_en": text,
                    "final_ko": final_ko,
                    "domain": domain,
                    "final_score": final_score,
                    "few_shot_context_used": bool(few_shot_ctx.strip()),
                    "motivation_injected": motivation_injected,
                    "companion_injected": companion_injected,
                    "cross_ref_injected": sec.get("cross_ref_injected", False),
                    "block_type": sec.get("block_type", "body"),
                    "abstraction_score": sec.get("abstraction_score", 0.0),
                    # Quality agent fields from Stage3
                    "fluency_detail": sec.get("fluency_detail"),
                    "bt_similarity": sec.get("bt_similarity"),
                    "naturalness_fixes": sec.get("naturalness_fixes"),
                    "score_trajectory": sec.get("score_trajectory"),
                })

                db.update_section(db_sec_id, status="completed")
                sec_logger.info(f"Section {sec_id} finalized, score={final_score}")

                processed.append({**sec, "db_section_id": db_sec_id})

            except Exception as exc:
                sec_logger.error(
                    f"Evolution failed for section {sec_id}: {exc}",
                    details={"traceback": traceback.format_exc()},
                )
                db.update_section(db_sec_id, status="failed")
                output_sections.append({
                    "section_id": sec_id,
                    "original_en": text,
                    "final_ko": final_ko,
                    "domain": domain,
                    "final_score": 0.0,
                    "few_shot_context_used": False,
                    "motivation_injected": False,
                })
                processed.append({**sec, "db_section_id": db_sec_id})

        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        # Build final output JSON
        output = {
            "job_id": job["id"],
            "pdf_path": job.get("pdf_path", ""),
            "pages": f"{job.get('start_page', 0)}-{job.get('end_page', 0)}",
            "sections": output_sections,
            "stats": {
                "section_count": len(output_sections),
                "avg_score": avg_score,
                "scored_sections": len(scores),
            },
        }

        os.makedirs("results", exist_ok=True)
        output_path = f"results/pipeline_{job['id']}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        # Generate LaTeX + compile to PDF
        tex_path = self._write_latex(output, job)
        pdf_path_out = self._compile_pdf(tex_path, logger)

        logger.info(
            f"Stage 5 complete — saved to {output_path}",
            details={
                "output_path": output_path,
                "tex_path": tex_path,
                "pdf_path": pdf_path_out,
                "section_count": len(output_sections),
                "avg_score": avg_score,
            },
        )

        return {
            "sections": processed,
            "output_path": output_path,
            "tex_path": tex_path,
            "pdf_path": pdf_path_out,
            "summary": {
                "section_count": len(output_sections),
                "avg_score": avg_score,
                "output_path": output_path,
                "tex_path": tex_path,
                "pdf_path": pdf_path_out,
            },
        }

    # ------------------------------------------------------------------
    # LaTeX renderer + PDF compiler
    # ------------------------------------------------------------------

    @staticmethod
    def _write_latex(output: dict, job: dict) -> str:
        """Convert pipeline JSON output to a bilingual XeLaTeX file (Korean-capable)."""
        job_id = job["id"]
        src_pdf = output.get("pdf_path", "")
        pages = output.get("pages", "")
        sections = output.get("sections", [])

        # Infer document title from source filename
        import os as _os
        src_basename = _os.path.splitext(_os.path.basename(src_pdf))[0]
        title_ko = src_basename.replace("_", " ").replace("-", " ").title()

        preamble = rf"""\documentclass[11pt,a4paper,oneside]{{memoir}}
% ── Korean / CJK fonts (XeLaTeX) ─────────────────────────────────────────
\usepackage{{fontspec}}
\usepackage{{xeCJK}}
\setCJKmainfont{{Noto Serif CJK KR}}[
  BoldFont   = Noto Serif CJK KR,
  ItalicFont = Noto Serif CJK KR
]
\setCJKsansfont{{Noto Sans CJK KR}}
\setmainfont{{DejaVu Serif}}[Scale=0.95]
\setsansfont{{DejaVu Sans}}[Scale=0.95]
\setmonofont{{DejaVu Sans Mono}}[Scale=0.85]

% ── Page layout (memoir) ─────────────────────────────────────────────────
\settrimmedsize{{297mm}}{{210mm}}{{*}}
\setlength{{\trimtop}}{{0pt}}
\setlength{{\trimedge}}{{\stockwidth}}
\addtolength{{\trimedge}}{{-\paperwidth}}
\settypeblocksize{{240mm}}{{150mm}}{{*}}
\setulmargins{{30mm}}{{*}}{{*}}
\setlrmargins{{30mm}}{{*}}{{*}}
\checkandfixthelayout

% ── Colours ──────────────────────────────────────────────────────────────
\usepackage{{xcolor}}
\definecolor{{ChapterBlue}}{{RGB}}{{30,70,130}}
\definecolor{{OrigBg}}{{RGB}}{{252,252,248}}
\definecolor{{KoBg}}{{RGB}}{{245,250,255}}
\definecolor{{OrigBorder}}{{RGB}}{{180,180,170}}
\definecolor{{KoBorder}}{{RGB}}{{100,150,200}}
\definecolor{{ScoreGreen}}{{RGB}}{{30,130,50}}
\definecolor{{ScoreOrange}}{{RGB}}{{200,100,0}}
\definecolor{{ScoreRed}}{{RGB}}{{180,30,30}}

% ── tcolorbox (callout boxes) ────────────────────────────────────────────
\usepackage{{tcolorbox}}
\tcbuselibrary{{skins,breakable}}

\tcbset{{
  origstyle/.style={{
    enhanced, breakable,
    colback=OrigBg, colframe=OrigBorder,
    fonttitle=\small\bfseries\sffamily,
    title={{원문 (English)}},
    boxrule=0.4pt, arc=2pt,
    left=6pt, right=6pt, top=4pt, bottom=4pt,
    coltitle=black
  }},
  kostyle/.style={{
    enhanced, breakable,
    colback=KoBg, colframe=KoBorder,
    fonttitle=\small\bfseries\sffamily,
    title={{번역 (Korean)}},
    boxrule=0.6pt, arc=2pt,
    left=6pt, right=6pt, top=4pt, bottom=4pt,
    coltitle=ChapterBlue
  }}
}}

% ── Chapter / Section style (memoir) ─────────────────────────────────────
\chapterstyle{{section}}
\setsecheadstyle{{\large\bfseries\sffamily\color{{ChapterBlue}}}}
\setsubsecheadstyle{{\normalsize\bfseries\sffamily}}

% ── Header / footer ──────────────────────────────────────────────────────
\makepagestyle{{bookstyle}}
\makeoddhead{{bookstyle}}{{\small\itshape {_tex_escape(title_ko)}}}{{}}{{\small\thepage}}
\makeevenhead{{bookstyle}}{{\small\thepage}}{{}}{{\small\itshape 번역 파이프라인}}
\makeheadrule{{bookstyle}}{{\textwidth}}{{0.4pt}}
\pagestyle{{bookstyle}}

% ── Hyperlinks ────────────────────────────────────────────────────────────
\usepackage{{hyperref}}
\hypersetup{{
  colorlinks=true, linkcolor=ChapterBlue,
  urlcolor=teal, pdfauthor={{Translation Pipeline}},
  pdftitle={{{_tex_escape(title_ko)}}}
}}

% ── Misc ─────────────────────────────────────────────────────────────────
\usepackage{{microtype}}
\usepackage{{parskip}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.5\baselineskip}}

\begin{{document}}

% ── Title page ───────────────────────────────────────────────────────────
\begin{{titlingpage}}
\vspace*{{3cm}}
{{\sffamily
  \begin{{center}}
    {{\color{{ChapterBlue}}\rule{{\textwidth}}{{2pt}}}}\\[1em]
    {{\Huge\bfseries {_tex_escape(title_ko)}}}\\[0.8em]
    {{\large 영한 기계번역 결과물}}\\[0.5em]
    {{\color{{ChapterBlue}}\rule{{\textwidth}}{{1pt}}}}\\[2em]
    {{\normalsize\ttfamily {_tex_escape(src_pdf)}}}\\[0.3em]
    {{\small 페이지 범위: {pages} \quad 섹션 수: {len(sections)}}}\\[0.5em]
    {{\small\color{{gray}} Job ID: \texttt{{{_tex_escape(job_id)}}}}}
  \end{{center}}
}}
\vfill
{{\small\color{{gray}} \textit{{본 문서는 PCM 번역 파이프라인으로 자동 생성되었습니다.\\
번역 품질 평가 포함: FluencyAgent (G-Eval), NaturalnessEditor, BackTranslationVerifier}}}}
\end{{titlingpage}}

\clearpage
\tableofcontents*
\clearpage

"""

        section_lines = []
        for i, sec in enumerate(sections, 1):
            raw_sec_id = str(sec.get("section_id", f"sec{i}"))
            sec_id_display = _tex_escape(raw_sec_id.replace("_chunk", " §").replace("_", " "))
            original = sec.get("original_en", "")
            korean = sec.get("final_ko", "")
            domain = sec.get("domain", "general")
            score = sec.get("final_score", 0.0)
            fluency = sec.get("fluency_detail", {})
            bt_sim = sec.get("bt_similarity")
            naturalness = sec.get("naturalness_fixes", [])

            score_color = (
                "ScoreGreen" if score >= 70
                else ("ScoreOrange" if score >= 45 else "ScoreRed")
            )

            # Quality badge line
            badge_parts = [
                rf"\textbf{{\color{{{score_color}}}점수: {score}}}",
                rf"\quad 도메인: \textit{{{_tex_escape(domain)}}}",
            ]
            if fluency:
                acc = fluency.get('accuracy', '?')
                flu = fluency.get('fluency', '?')
                tone = fluency.get('tone', '?')
                term = fluency.get('terminology', '?')
                badge_parts.append(
                    rf"\quad {{\small acc={acc} flu={flu} tone={tone} term={term}}}"
                )
            if bt_sim is not None:
                bt_color = "ScoreGreen" if bt_sim >= 0.55 else "ScoreRed"
                badge_parts.append(rf"\quad \textcolor{{{bt_color}}}{{BT: {bt_sim:.2f}}}")
            if naturalness:
                badge_parts.append(rf"\quad \textcolor{{gray}}{{\small ✎ {', '.join(naturalness[:2])}}}")

            # Clean Korean text for LaTeX
            ko_clean = _clean_latex_blocks(korean)
            orig_clean = _tex_escape(original[:1000]) + (r"\ldots" if len(original) > 1000 else "")

            section_lines += [
                rf"\section{{{sec_id_display}}}",
                r"\noindent " + " ".join(badge_parts),
                r"\vspace{0.4em}",
                r"",
                r"\begin{tcolorbox}[origstyle]",
                r"\small " + orig_clean,
                r"\end{tcolorbox}",
                r"\vspace{0.3em}",
                r"",
                r"\begin{tcolorbox}[kostyle]",
                ko_clean[:3000] + (r"\ldots" if len(ko_clean) > 3000 else ""),
                r"\end{tcolorbox}",
                r"\vspace{0.8em}",
                r"",
            ]

        footer = r"\end{document}" + "\n"

        tex_path = f"results/pipeline_{job_id}.tex"
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(preamble)
            f.write("\n".join(section_lines))
            f.write("\n" + footer)

        return tex_path

    @staticmethod
    def _compile_pdf(tex_path: str, logger) -> str:
        """Compile .tex → .pdf using xelatex. Returns pdf path or empty string on failure."""
        import subprocess
        import shutil

        if not shutil.which("xelatex"):
            logger.warning("xelatex not found — skipping PDF compilation")
            return ""

        tex_dir = os.path.dirname(os.path.abspath(tex_path))
        tex_file = os.path.basename(tex_path)
        pdf_path = tex_path.replace(".tex", ".pdf")

        try:
            # Run twice for ToC page numbers
            for run in range(2):
                result = subprocess.run(
                    [
                        "xelatex",
                        "-interaction=nonstopmode",
                        "-output-directory", tex_dir,
                        tex_file,
                    ],
                    cwd=tex_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0 and run == 1:
                    # Log last 20 lines of xelatex output for diagnosis
                    err_lines = (result.stdout + result.stderr).strip().splitlines()[-20:]
                    logger.warning(
                        f"xelatex exited {result.returncode} — PDF may be incomplete",
                        details={"xelatex_tail": "\n".join(err_lines)},
                    )

            if os.path.exists(pdf_path):
                logger.info(f"PDF compiled: {pdf_path}")
                # Clean up auxiliary files
                for ext in (".aux", ".log", ".toc", ".out"):
                    aux = pdf_path.replace(".pdf", ext)
                    if os.path.exists(aux):
                        os.remove(aux)
                return pdf_path

            logger.warning(f"PDF not produced at {pdf_path}")
            return ""

        except Exception as exc:
            logger.warning(f"PDF compilation failed: {exc}")
            return ""


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _tex_escape(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _clean_latex_blocks(text: str) -> str:
    r"""Prepare Korean translation text for LaTeX tcolorbox output.

    - Removes internal pipeline markup (\begin{linkbox}...\end{linkbox})
    - Converts Markdown bold/italic to LaTeX commands
    - Preserves math delimiters $...$ and \(...\)
    - Escapes remaining special characters (except already-escaped math)
    """
    import re as _re

    # 1. Strip pipeline linkbox markup
    text = _re.sub(
        r"\\begin\{linkbox\}.*?\\end\{linkbox\}", "", text,
        flags=_re.DOTALL
    ).strip()

    # 2. Strip HTML-style comments
    text = _re.sub(r"<!--.*?-->", "", text, flags=_re.DOTALL)

    # 3. Convert Markdown **bold** → \textbf{} and *italic* → \textit{}
    text = _re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = _re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)

    # 4. Convert Markdown ## headers → bold lines
    text = _re.sub(r"^#{1,3}\s+(.+)$", r"\\textbf{\1}", text, flags=_re.MULTILINE)

    # 5. Protect math spans before escaping
    # Replace $...$ with placeholders
    math_spans: list[str] = []
    def _stash_math(m):
        math_spans.append(m.group(0))
        return f"MATHPLACEHOLDER{len(math_spans)-1}ENDMATH"

    text = _re.sub(r"\$[^$\n]+?\$", _stash_math, text)
    text = _re.sub(r"\\\(.+?\\\)", _stash_math, text)

    # 6. Escape LaTeX special chars (excluding already-processed \textbf etc.)
    #    Only escape characters that aren't part of a LaTeX command
    for char, esc in [("&", r"\&"), ("%", r"\%"), ("#", r"\#"),
                       ("_", r"\_"), ("~", r"\textasciitilde{}"),
                       ("^", r"\textasciicircum{}")]:
        # Don't escape inside \textbf{} or \textit{} arguments — simple heuristic
        text = _re.sub(rf"(?<!\\){_re.escape(char)}", esc, text)

    # 7. Restore math placeholders
    for idx, span in enumerate(math_spans):
        text = text.replace(f"MATHPLACEHOLDER{idx}ENDMATH", span)

    # 8. Convert double-newlines to LaTeX paragraph breaks
    text = _re.sub(r"\n{2,}", "\n\n", text)

    return text
