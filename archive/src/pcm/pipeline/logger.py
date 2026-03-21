"""
Structured agent logger that wraps PipelineDB.log() with context.
"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.pcm.pipeline.db import PipelineDB


class PipelineLogger:
    """Wraps PipelineDB.log() with context for a specific job/stage/section."""

    def __init__(
        self,
        db: "PipelineDB",
        job_id: str,
        stage_num: Optional[int] = None,
        section_id: Optional[str] = None,
        agent_name: str = "Pipeline",
    ):
        self._db = db
        self._job_id = job_id
        self._stage_num = stage_num
        self._section_id = section_id
        self._agent_name = agent_name

    def info(self, message: str, details: Optional[dict] = None):
        self._db.log(
            job_id=self._job_id,
            agent_name=self._agent_name,
            level="INFO",
            message=message,
            stage_num=self._stage_num,
            section_id=self._section_id,
            details=details,
        )

    def warning(self, message: str, details: Optional[dict] = None):
        self._db.log(
            job_id=self._job_id,
            agent_name=self._agent_name,
            level="WARNING",
            message=message,
            stage_num=self._stage_num,
            section_id=self._section_id,
            details=details,
        )

    def error(self, message: str, details: Optional[dict] = None):
        self._db.log(
            job_id=self._job_id,
            agent_name=self._agent_name,
            level="ERROR",
            message=message,
            stage_num=self._stage_num,
            section_id=self._section_id,
            details=details,
        )

    def bind(
        self,
        section_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> "PipelineLogger":
        """Return a new logger with updated context for section-level logging."""
        return PipelineLogger(
            db=self._db,
            job_id=self._job_id,
            stage_num=self._stage_num,
            section_id=section_id if section_id is not None else self._section_id,
            agent_name=agent_name if agent_name is not None else self._agent_name,
        )
