"""
SQLite-based pipeline state manager for the MasterPipeline.
"""

import json
import sqlite3
import datetime
from typing import Optional


class PipelineDB:
    """Thread-safe SQLite manager for pipeline state."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        pdf_path TEXT NOT NULL,
        start_page INTEGER NOT NULL,
        end_page INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        config TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS stages (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        stage_num INTEGER NOT NULL,
        stage_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        started_at TEXT,
        completed_at TEXT,
        error_message TEXT,
        output_summary TEXT DEFAULT '{}',
        FOREIGN KEY (job_id) REFERENCES jobs(id)
    );

    CREATE TABLE IF NOT EXISTS sections (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        stage_id TEXT NOT NULL,
        section_id TEXT NOT NULL,
        original_en TEXT,
        final_ko TEXT,
        wsd_domain TEXT,
        final_score REAL DEFAULT 0.0,
        status TEXT NOT NULL DEFAULT 'pending',
        started_at TEXT,
        completed_at TEXT,
        FOREIGN KEY (job_id) REFERENCES jobs(id),
        FOREIGN KEY (stage_id) REFERENCES stages(id)
    );

    CREATE TABLE IF NOT EXISTS iterations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        section_id TEXT NOT NULL,
        job_id TEXT NOT NULL,
        iteration_num INTEGER NOT NULL,
        agent_name TEXT NOT NULL,
        translated_text TEXT,
        score REAL,
        critique TEXT,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (section_id) REFERENCES sections(id)
    );

    CREATE TABLE IF NOT EXISTS agent_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL,
        section_id TEXT,
        stage_num INTEGER,
        agent_name TEXT NOT NULL,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        details TEXT DEFAULT '{}',
        timestamp TEXT NOT NULL
    );
    """

    def __init__(self, db_path: str = "pipeline.db"):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(self.SCHEMA)
            conn.commit()

    def _now(self) -> str:
        return datetime.datetime.utcnow().isoformat()

    def _row_to_dict(self, row) -> Optional[dict]:
        if row is None:
            return None
        return dict(row)

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def create_job(
        self,
        pdf_path: str,
        start_page: int,
        end_page: int,
        config: Optional[dict] = None,
    ) -> str:
        now = self._now()
        date_str = datetime.datetime.utcnow().strftime("%Y%m%d")

        # Find how many jobs were created today for a sequential suffix
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE id LIKE ?",
                (f"job_{date_str}_%",),
            )
            count = cursor.fetchone()[0]
            job_id = f"job_{date_str}_{count + 1:03d}"

            conn.execute(
                """INSERT INTO jobs (id, pdf_path, start_page, end_page, status,
                   created_at, updated_at, config)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)""",
                (
                    job_id,
                    pdf_path,
                    start_page,
                    end_page,
                    now,
                    now,
                    json.dumps(config or {}),
                ),
            )
            conn.commit()
        return job_id

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row_to_dict(row)

    def update_job_status(self, job_id: str, status: str):
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, job_id),
            )
            conn.commit()

    def list_jobs(self) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------

    def get_or_create_stage(
        self, job_id: str, stage_num: int, stage_name: str
    ) -> dict:
        stage_id = f"{job_id}_stage_{stage_num}"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM stages WHERE id = ?", (stage_id,)
            ).fetchone()
            if row:
                return self._row_to_dict(row)

            now = self._now()
            conn.execute(
                """INSERT INTO stages
                   (id, job_id, stage_num, stage_name, status, output_summary)
                   VALUES (?, ?, ?, ?, 'pending', '{}')""",
                (stage_id, job_id, stage_num, stage_name),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM stages WHERE id = ?", (stage_id,)
            ).fetchone()
        return self._row_to_dict(row)

    def update_stage_status(
        self,
        stage_id: str,
        status: str,
        error_message: Optional[str] = None,
        output_summary: Optional[dict] = None,
    ):
        now = self._now()
        with self._connect() as conn:
            if status == "running":
                conn.execute(
                    "UPDATE stages SET status = ?, started_at = ? WHERE id = ?",
                    (status, now, stage_id),
                )
            elif status in ("completed", "failed", "skipped"):
                summary_str = json.dumps(output_summary or {})
                conn.execute(
                    """UPDATE stages
                       SET status = ?, completed_at = ?, error_message = ?,
                           output_summary = ?
                       WHERE id = ?""",
                    (status, now, error_message, summary_str, stage_id),
                )
            else:
                conn.execute(
                    "UPDATE stages SET status = ? WHERE id = ?",
                    (status, stage_id),
                )
            conn.commit()

    def get_stages_for_job(self, job_id: str) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM stages WHERE job_id = ? ORDER BY stage_num",
                (job_id,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def create_section(
        self,
        job_id: str,
        stage_id: str,
        section_id: str,
        original_en: str,
    ) -> str:
        pk = f"{job_id}_{section_id}"
        now = self._now()
        with self._connect() as conn:
            # Upsert: if already exists, just return the id
            existing = conn.execute(
                "SELECT id FROM sections WHERE id = ?", (pk,)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO sections
                       (id, job_id, stage_id, section_id, original_en, status, started_at)
                       VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                    (pk, job_id, stage_id, section_id, original_en, now),
                )
                conn.commit()
        return pk

    def update_section(self, section_id: str, **kwargs):
        if not kwargs:
            return
        now = self._now()
        kwargs.setdefault("completed_at", now)
        allowed = {
            "final_ko", "wsd_domain", "final_score", "status",
            "started_at", "completed_at",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [section_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE sections SET {set_clause} WHERE id = ?", values
            )
            conn.commit()

    def get_sections_for_stage(self, stage_id: str) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sections WHERE stage_id = ? ORDER BY id",
                (stage_id,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_sections_for_job(self, job_id: str) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sections WHERE job_id = ? ORDER BY id",
                (job_id,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Iterations
    # ------------------------------------------------------------------

    def add_iteration(
        self,
        section_id: str,
        job_id: str,
        iteration_num: int,
        agent_name: str,
        translated_text: Optional[str],
        score: Optional[float],
        critique: Optional[str],
    ) -> int:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO iterations
                   (section_id, job_id, iteration_num, agent_name,
                    translated_text, score, critique, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    section_id,
                    job_id,
                    iteration_num,
                    agent_name,
                    translated_text,
                    score,
                    critique,
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def log(
        self,
        job_id: str,
        agent_name: str,
        level: str,
        message: str,
        stage_num: Optional[int] = None,
        section_id: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        now = self._now()
        details_str = json.dumps(details or {})
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_logs
                   (job_id, section_id, stage_num, agent_name, level,
                    message, details, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    section_id,
                    stage_num,
                    agent_name,
                    level.upper(),
                    message,
                    details_str,
                    now,
                ),
            )
            conn.commit()

    def get_logs(
        self,
        job_id: str,
        level: Optional[str] = None,
        stage_num: Optional[int] = None,
    ) -> list:
        query = "SELECT * FROM agent_logs WHERE job_id = ?"
        params: list = [job_id]
        if level:
            query += " AND level = ?"
            params.append(level.upper())
        if stage_num is not None:
            query += " AND stage_num = ?"
            params.append(stage_num)
        query += " ORDER BY timestamp"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_job_summary(self, job_id: str) -> dict:
        job = self.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found"}

        stages = self.get_stages_for_job(job_id)
        sections = self.get_sections_for_job(job_id)

        section_stats = {
            "total": len(sections),
            "completed": sum(1 for s in sections if s["status"] == "completed"),
            "failed": sum(1 for s in sections if s["status"] == "failed"),
            "pending": sum(1 for s in sections if s["status"] == "pending"),
        }

        scores = [s["final_score"] for s in sections if s["final_score"]]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        return {
            "job": job,
            "stages": stages,
            "section_stats": section_stats,
            "avg_score": avg_score,
        }
