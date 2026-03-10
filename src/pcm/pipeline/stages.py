"""
Five pipeline stage implementations for the MasterPipeline.

Each stage:
  - Accepts sections_text: list of {"section_id": str, "text": str}
  - Returns: {"sections": [...processed...], "summary": {...}}
  - Never raises — catches exceptions, logs them, marks section as "failed"
"""

from __future__ import annotations

import json
import time
import traceback
from typing import TYPE_CHECKING

import requests

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
                except Exception:
                    sec.setdefault("block_type", "body")
                    sec.setdefault("blocks_metadata", {})
            # Compute abstraction_score from LaTeX density + math term frequency
            if "abstraction_score" not in sec:
                try:
                    from src.pcm.core.semantic_chunker import SemanticChunker
                    sec["abstraction_score"] = SemanticChunker()._compute_abstraction_score(text)
                except Exception:
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

    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL = "qwen2.5:7b"
    SYSTEM_PROMPT = (
        "당신은 수학/물리 전문 번역가입니다. "
        "수식($...$)은 절대 변형하지 마세요. "
        "주어진 용어 사전을 반드시 따르세요."
    )

    def _translate(self, text: str, terminology_guide: str) -> str:
        full_prompt = (
            f"{self.SYSTEM_PROMPT}\n\n"
            f"{terminology_guide}\n\n"
            f"다음 영어 수학/물리 텍스트를 한국어로 번역하세요:\n\n{text}"
        )
        payload = {
            "model": self.MODEL,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        resp = requests.post(self.OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

    def run(self, job, stage, sections_text, db, logger):
        processed = []

        logger.info(
            f"Stage 2 starting: {len(sections_text)} sections",
            details={"section_count": len(sections_text)},
        )

        for sec in sections_text:
            sec_id = sec["section_id"]
            text = sec.get("text", "")
            domain = sec.get("domain", "general")
            terminology_guide = sec.get("terminology_guide", "")
            db_sec_id = sec.get("db_section_id") or f"{job['id']}_{sec_id}"

            sec_logger = logger.bind(
                section_id=db_sec_id, agent_name="InitialTranslator"
            )
            db.update_section(db_sec_id, status="running")

            t_start = time.time()
            try:
                draft_ko = self._translate(text, terminology_guide)
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
                db.update_section(
                    db_sec_id,
                    final_ko=draft_ko,
                    status="completed",
                )

                sec_logger.info(
                    f"Section {sec_id} drafted in {elapsed}s",
                    details={"elapsed_s": elapsed, "domain": domain},
                )

                processed.append({
                    **sec,
                    "draft_ko": draft_ko,
                    "db_section_id": db_sec_id,
                })

            except requests.exceptions.Timeout:
                elapsed = round(time.time() - t_start, 2)
                sec_logger.warning(
                    f"Ollama timeout for section {sec_id} after {elapsed}s — keeping English",
                    details={"elapsed_s": elapsed},
                )
                db.update_section(db_sec_id, final_ko=text, status="completed")
                processed.append({**sec, "draft_ko": text, "db_section_id": db_sec_id})

            except Exception as exc:
                elapsed = round(time.time() - t_start, 2)
                sec_logger.error(
                    f"Draft failed for section {sec_id}: {exc}",
                    details={"traceback": traceback.format_exc(), "elapsed_s": elapsed},
                )
                db.update_section(db_sec_id, final_ko=text, status="failed")
                processed.append({**sec, "draft_ko": text, "db_section_id": db_sec_id})

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

        km = KnowledgeManager()
        tcr = TCRLoop(
            model="qwen2.5:7b",
            threshold=self.THRESHOLD,
            max_iterations=self.MAX_ITERATIONS,
        )

        processed = []

        logger.info(
            f"Stage 3 starting: {len(sections_text)} sections",
            details={"section_count": len(sections_text)},
        )

        for sec in sections_text:
            sec_id = sec["section_id"]
            text = sec.get("text", "")
            domain = sec.get("domain", "general")
            draft_ko = sec.get("draft_ko", text)
            terminology_guide = sec.get("terminology_guide", "")
            db_sec_id = sec.get("db_section_id") or f"{job['id']}_{sec_id}"

            sec_logger = logger.bind(
                section_id=db_sec_id, agent_name="TCRLoop"
            )
            db.update_section(db_sec_id, status="running")

            try:
                glossary = km.get_all_for_domain(domain)

                # Gather few-shot feedback examples for this section
                feedback_context = ""
                try:
                    from src.pcm.core.feedback_loop import FeedbackInjector, FeedbackDB
                    _injector = FeedbackInjector(FeedbackDB())
                    feedback_context = _injector.inject_to_translator_prompt(
                        sec_id, top_k=3
                    )
                except Exception:
                    feedback_context = ""

                initial_prompt = (
                    "당신은 수학/물리 전문 번역가입니다. "
                    "수식($...$)은 절대 변형하지 마세요. 학술 문체를 사용하세요.\n\n"
                    f"{terminology_guide}\n\n"
                    f"{feedback_context}"
                )

                final_ko, trace = tcr.run(
                    original_en=text,
                    glossary=glossary,
                    initial_prompt=initial_prompt,
                )

                iterations = trace.get("iterations", [])
                scores = [it.get("score", 0) for it in iterations]

                # Persist each iteration
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

                final_score = scores[-1] if scores else 0.0
                score_trajectory = "→".join(str(s) for s in scores)

                if scores and scores[-1] < self.THRESHOLD:
                    sec_logger.warning(
                        f"Section {sec_id}: max_iter_reached, score={final_score}",
                        details={"scores": scores, "trajectory": score_trajectory},
                    )
                else:
                    sec_logger.info(
                        f"Section {sec_id}: {score_trajectory} (passed)",
                        details={"scores": scores, "final_score": final_score},
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
                    "db_section_id": db_sec_id,
                })

            except Exception as exc:
                sec_logger.error(
                    f"TCR failed for section {sec_id}: {exc}",
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

        km = KnowledgeManager()
        cm = ConsistencyManager()

        dominant = self._dominant_domain(sections_text)
        glossary = km.get_all_for_domain(dominant)

        total_inconsistencies = 0
        fixed_count = 0
        processed = []

        logger.info(
            f"Stage 4 starting: dominant_domain={dominant}, "
            f"{len(sections_text)} sections",
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

                db.update_section(
                    db_sec_id,
                    final_ko=fixed_ko,
                    status="completed",
                )

                processed.append({
                    **sec,
                    "final_ko": fixed_ko,
                    "db_section_id": db_sec_id,
                })

            except Exception as exc:
                sec_logger.error(
                    f"Consistency check failed for section {sec_id}: {exc}",
                    details={"traceback": traceback.format_exc()},
                )
                db.update_section(db_sec_id, status="failed")
                processed.append({**sec, "db_section_id": db_sec_id})

        logger.info(
            "Stage 4 complete",
            details={
                "total_inconsistencies": total_inconsistencies,
                "fixed_count": fixed_count,
            },
        )

        return {
            "sections": processed,
            "summary": {
                "section_count": len(processed),
                "total_inconsistencies": total_inconsistencies,
                "fixed_count": fixed_count,
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
        import os

        feedback_db = FeedbackDB()
        injector = FeedbackInjector(db=feedback_db)

        # MotivationAgent — loaded once, used per-section
        try:
            from src.pcm.core.motivation_agent import MotivationAgent
            motivation_agent = MotivationAgent()
        except Exception:
            motivation_agent = None

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
                                final_ko = motivation_agent.inject_into_translation(
                                    final_ko, motivation
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
                    "block_type": sec.get("block_type", "body"),
                    "abstraction_score": sec.get("abstraction_score", 0.0),
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

        logger.info(
            f"Stage 5 complete — saved to {output_path}",
            details={
                "output_path": output_path,
                "section_count": len(output_sections),
                "avg_score": avg_score,
            },
        )

        return {
            "sections": processed,
            "output_path": output_path,
            "summary": {
                "section_count": len(output_sections),
                "avg_score": avg_score,
                "output_path": output_path,
            },
        }
