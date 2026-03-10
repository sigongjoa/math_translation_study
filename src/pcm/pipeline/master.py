"""
MasterPipeline orchestrator — runs all 5 stages end-to-end with
job resumption, stage skipping, and full error isolation.
"""

from __future__ import annotations

import json
import traceback
from typing import Optional

from src.pcm.pipeline.db import PipelineDB
from src.pcm.pipeline.logger import PipelineLogger
from src.pcm.pipeline.stages import (
    Stage1_Orientation,
    Stage2_Drafting,
    Stage3_Refinement,
    Stage4_Validation,
    Stage5_Evolution,
)


class MasterPipeline:
    """Orchestrates the 5-stage translation pipeline with SQLite state tracking."""

    def __init__(self, db_path: str = "pipeline.db"):
        self.db = PipelineDB(db_path)
        self.stages = [
            Stage1_Orientation(),
            Stage2_Drafting(),
            Stage3_Refinement(),
            Stage4_Validation(),
            Stage5_Evolution(),
        ]

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        pdf_path: str,
        start_page: int,
        end_page: int,
        job_id: Optional[str] = None,
        sections_override: Optional[list] = None,
    ) -> str:
        """
        Run or resume a pipeline job.

        Parameters
        ----------
        pdf_path : str
            Path to the source PDF (may be a placeholder for demo/override runs).
        start_page : int
            First page (0-indexed) of the range to process.
        end_page : int
            Last page (exclusive) of the range to process.
        job_id : str, optional
            If given, resume an existing job instead of creating a new one.
        sections_override : list, optional
            List of {"section_id": str, "text": str} dicts.
            When provided the PDF is not parsed at all.

        Returns
        -------
        str
            The job_id of the completed (or partially completed) job.
        """
        # 1. Create or resume job ----------------------------------------
        if job_id:
            job = self.db.get_job(job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found in database")
            print(f"[RESUME] Resuming job {job_id}")
        else:
            job_id = self.db.create_job(pdf_path, start_page, end_page)
            job = self.db.get_job(job_id)
            print(
                f"[START] New job {job_id}: {pdf_path} pages {start_page}-{end_page}"
            )

        # 2. Parse sections (or use override) ----------------------------
        if sections_override is not None:
            sections_text = sections_override
        else:
            sections_text = self._parse_pdf(pdf_path, start_page, end_page, job_id)

        self.db.update_job_status(job_id, "running")

        # 3. Run stages ---------------------------------------------------
        stage_output: dict = {"sections": sections_text}

        for stage in self.stages:
            stage_record = self.db.get_or_create_stage(
                job_id, stage.stage_num, stage.stage_name
            )
            logger = PipelineLogger(
                self.db, job_id, stage_num=stage.stage_num
            )

            if stage_record["status"] == "completed":
                print(
                    f"[SKIP] Stage {stage.stage_num} ({stage.stage_name}) "
                    "already completed"
                )
                # Reload previous output so downstream stages have correct data
                saved_summary = stage_record.get("output_summary", "{}")
                if isinstance(saved_summary, str):
                    saved_summary = json.loads(saved_summary)
                stage_output = saved_summary
                if "sections" not in stage_output:
                    stage_output["sections"] = sections_text
                continue

            print(f"[RUN] Stage {stage.stage_num}: {stage.stage_name}")
            self.db.update_stage_status(stage_record["id"], "running")

            try:
                result = stage.run(
                    job,
                    stage_record,
                    stage_output.get("sections", sections_text),
                    self.db,
                    logger,
                )
                stage_output = result

                # Store a compact summary (avoid bloating the DB with full text)
                summary = {
                    "section_count": len(result.get("sections", [])),
                    **result.get("summary", {}),
                }
                self.db.update_stage_status(
                    stage_record["id"], "completed", output_summary=summary
                )
                print(f"[DONE] Stage {stage.stage_num} completed: {summary}")

            except Exception as exc:
                err_tb = traceback.format_exc()
                logger.error(
                    f"Stage {stage.stage_num} failed: {exc}",
                    details={"traceback": err_tb},
                )
                self.db.update_stage_status(
                    stage_record["id"], "failed", error_message=str(exc)
                )
                print(
                    f"[FAIL] Stage {stage.stage_num} failed: {exc} — continuing"
                )
                # Keep previous stage_output so the next stage has something to work with

        self.db.update_job_status(job_id, "completed")
        print(f"[COMPLETE] Job {job_id} finished")
        return job_id

    # ------------------------------------------------------------------
    # PDF parsing
    # ------------------------------------------------------------------

    def _parse_pdf(
        self,
        pdf_path: str,
        start_page: int,
        end_page: int,
        job_id: str,
    ) -> list:
        """Parse PDF into sections using PDFStructureAnalyzer."""
        try:
            from src.pcm.core.structure_analyzer import PDFStructureAnalyzer

            analyzer = PDFStructureAnalyzer(pdf_path)
            elements = analyzer.extract_structure(start_page, end_page)

            sections: list[dict] = []
            current_section_id = "intro"
            current_text_parts: list[str] = []

            def flush():
                nonlocal current_text_parts
                if current_text_parts:
                    combined = " ".join(current_text_parts).strip()
                    if combined:
                        sections.append(
                            {"section_id": current_section_id, "text": combined}
                        )
                    current_text_parts = []

            for el in elements:
                el_type = el.get("type", "text")
                content = el.get("content", "")
                if el_type == "section":
                    flush()
                    current_section_id = el.get("id", content.split()[0])
                    current_text_parts = [content]
                elif el_type == "subsection":
                    flush()
                    current_section_id = el.get("id", content.split()[0])
                    current_text_parts = [content]
                else:
                    current_text_parts.append(content)

            flush()

            if not sections:
                # Fallback: treat entire range as one section
                all_text = " ".join(
                    el.get("content", "") for el in elements
                ).strip()
                sections = [{"section_id": "full", "text": all_text}]

            print(
                f"[PARSE] Extracted {len(sections)} sections from "
                f"{pdf_path} pages {start_page}-{end_page}"
            )
            return sections

        except Exception as exc:
            tb = traceback.format_exc()
            print(f"[PARSE ERROR] Failed to parse PDF: {exc}\n{tb}")
            # Return a single fallback section so the pipeline can still run
            return [
                {
                    "section_id": "parse_error",
                    "text": (
                        f"[PDF parse failed: {exc}] "
                        f"Source: {pdf_path} pages {start_page}-{end_page}"
                    ),
                }
            ]

    # ------------------------------------------------------------------
    # Status & listing utilities
    # ------------------------------------------------------------------

    def status(self, job_id: str):
        """Print a status tree for a job."""
        summary = self.db.get_job_summary(job_id)
        if "error" in summary:
            print(summary["error"])
            return

        job = summary["job"]
        print(f"\n{'='*60}")
        print(f"Job:    {job['id']}")
        print(f"PDF:    {job['pdf_path']}")
        print(
            f"Pages:  {job['start_page']}-{job['end_page']}"
        )
        print(f"Status: {job['status']}")
        print(f"Created:{job['created_at']}")
        print(f"Updated:{job['updated_at']}")
        print(f"{'─'*60}")

        print("Stages:")
        for s in summary.get("stages", []):
            status_icon = {
                "completed": "✓",
                "running": "►",
                "failed": "✗",
                "pending": "○",
                "skipped": "—",
            }.get(s["status"], "?")
            print(
                f"  [{status_icon}] Stage {s['stage_num']}: {s['stage_name']} "
                f"({s['status']})"
            )
            if s.get("error_message"):
                print(f"       ERROR: {s['error_message']}")

        sec_stats = summary.get("section_stats", {})
        print(f"{'─'*60}")
        print(
            f"Sections: {sec_stats.get('total', 0)} total | "
            f"{sec_stats.get('completed', 0)} done | "
            f"{sec_stats.get('failed', 0)} failed"
        )
        print(f"Avg score: {summary.get('avg_score', 0.0)}")
        print(f"{'='*60}\n")

    def list_jobs(self):
        """List all jobs with a status summary."""
        jobs = self.db.list_jobs()
        if not jobs:
            print("No jobs found.")
            return

        print(f"\n{'ID':<30} {'STATUS':<12} {'PDF':<40} {'CREATED'}")
        print("─" * 110)
        for j in jobs:
            pdf_short = j["pdf_path"]
            if len(pdf_short) > 38:
                pdf_short = "..." + pdf_short[-35:]
            print(
                f"{j['id']:<30} {j['status']:<12} "
                f"{pdf_short:<40} {j['created_at'][:19]}"
            )
        print()
