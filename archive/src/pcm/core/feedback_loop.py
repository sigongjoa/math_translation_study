"""
Feedback Loop System for PCM Translation Pipeline.

Captures human corrections to translations, stores them, scores their impact,
and injects relevant examples into translator prompts to improve future output.
"""

import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


VALID_FEEDBACK_TYPES = ("term", "style", "logic", "analogy", "structure")

DEFAULT_FEEDBACK_DIR = Path(__file__).parent.parent / "data" / "feedback"
DEFAULT_CORRECTIONS_FILE = DEFAULT_FEEDBACK_DIR / "corrections.json"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FeedbackEntry:
    """A single human correction captured during the review cycle."""

    feedback_id: str
    section_id: str
    feedback_type: str          # one of VALID_FEEDBACK_TYPES
    original: str               # text before correction
    corrected: str              # text after correction
    notes: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    impact_score: float = 0.0   # filled in by ImpactScorer

    def __post_init__(self):
        if self.feedback_type not in VALID_FEEDBACK_TYPES:
            raise ValueError(
                f"Invalid feedback_type '{self.feedback_type}'. "
                f"Must be one of {VALID_FEEDBACK_TYPES}."
            )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FeedbackEntry":
        return cls(**d)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class FeedbackDB:
    """
    JSON-backed, thread-safe store for FeedbackEntry objects.

    All data is persisted to ``src/pcm/data/feedback/corrections.json``.
    """

    def __init__(self, feedback_dir: Optional[Path] = None):
        self._dir = Path(feedback_dir) if feedback_dir else DEFAULT_FEEDBACK_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "corrections.json"
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        with self._lock:
            if self._path.exists():
                with open(self._path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self._entries: list[FeedbackEntry] = [
                    FeedbackEntry.from_dict(d) for d in raw.get("corrections", [])
                ]
            else:
                self._entries = []
                self._persist_unlocked()

    def _persist_unlocked(self):
        payload = {
            "corrections": [e.to_dict() for e in self._entries],
            "metadata": {
                "total": len(self._entries),
                "last_updated": datetime.utcnow().isoformat(),
            },
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # Public API ------------------------------------------------------------

    def add(self, entry: FeedbackEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            self._persist_unlocked()

    def all(self) -> list[FeedbackEntry]:
        with self._lock:
            return list(self._entries)

    def for_section(self, section_id: str) -> list[FeedbackEntry]:
        with self._lock:
            return [e for e in self._entries if e.section_id == section_id]

    def for_type(self, feedback_type: str) -> list[FeedbackEntry]:
        with self._lock:
            return [e for e in self._entries if e.feedback_type == feedback_type]

    def get_stats(self) -> dict:
        with self._lock:
            total = len(self._entries)
            by_type: dict = {}
            for entry in self._entries:
                by_type[entry.feedback_type] = by_type.get(entry.feedback_type, 0) + 1
            # Most frequent corrections: (original, corrected) pairs
            freq: dict = {}
            for entry in self._entries:
                key = f"{entry.original} → {entry.corrected}"
                freq[key] = freq.get(key, 0) + 1
            most_frequent = sorted(freq.items(), key=lambda x: -x[1])[:10]
        return {
            "total_corrections": total,
            "by_type": by_type,
            "most_frequent": most_frequent,
        }

    def next_id(self) -> str:
        with self._lock:
            return f"fb_{len(self._entries) + 1:04d}"


# ---------------------------------------------------------------------------
# Processors
# ---------------------------------------------------------------------------

class FeedbackProcessor:
    """
    Converts stored feedback entries into few-shot examples and prompt
    library updates.
    """

    def to_few_shot_example(self, entry: FeedbackEntry) -> str:
        """
        Render a FeedbackEntry as a markdown few-shot block for prompt injection.

        Example output:
            ### Correction example (term, section 2.3)
            BEFORE: 장
            AFTER:  체
            NOTE:   대수학 문맥
        """
        lines = [
            f"### Correction example ({entry.feedback_type}, section {entry.section_id})",
            f"BEFORE: {entry.original}",
            f"AFTER:  {entry.corrected}",
        ]
        if entry.notes:
            lines.append(f"NOTE:   {entry.notes}")
        return "\n".join(lines)

    def update_prompt_library(
        self, entries: list[FeedbackEntry], library_path: Optional[Path] = None
    ) -> dict:
        """
        Build (or update) a JSON prompt library from a list of feedback entries.

        Returns the full library dict and optionally writes it to *library_path*.
        """
        if library_path is None:
            library_path = DEFAULT_FEEDBACK_DIR / "prompt_library.json"

        library: dict = {}
        if Path(library_path).exists():
            with open(library_path, "r", encoding="utf-8") as f:
                library = json.load(f)

        for entry in entries:
            key = f"{entry.section_id}:{entry.feedback_type}"
            if key not in library:
                library[key] = []
            example = self.to_few_shot_example(entry)
            if example not in library[key]:
                library[key].append(example)

        library["_metadata"] = {
            "total_examples": sum(len(v) for v in library.values() if isinstance(v, list)),
            "last_updated": datetime.utcnow().isoformat(),
        }

        with open(library_path, "w", encoding="utf-8") as f:
            json.dump(library, f, ensure_ascii=False, indent=2)

        return library


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class ImpactScorer:
    """
    Assigns an impact score (0.0–1.0) to each FeedbackEntry based on heuristics.

    Scoring criteria:
        - feedback_type weight: term=1.0, logic=0.9, style=0.6, analogy=0.5, structure=0.7
        - length of the correction (longer corrections score higher)
        - presence of notes (small bonus)
    """

    TYPE_WEIGHTS = {
        "term": 1.0,
        "logic": 0.9,
        "structure": 0.7,
        "style": 0.6,
        "analogy": 0.5,
    }

    def score(self, entry: FeedbackEntry) -> float:
        base = self.TYPE_WEIGHTS.get(entry.feedback_type, 0.5)
        # Normalise correction length: each 10 chars contributes up to 0.1
        length_bonus = min(0.2, len(entry.corrected) / 100.0)
        notes_bonus = 0.1 if entry.notes else 0.0
        raw = base + length_bonus + notes_bonus
        return round(min(1.0, raw), 3)

    def score_all(self, entries: list[FeedbackEntry]) -> list[FeedbackEntry]:
        """Return the same list with impact_score filled in."""
        for entry in entries:
            entry.impact_score = self.score(entry)
        return entries


# ---------------------------------------------------------------------------
# Injector
# ---------------------------------------------------------------------------

class FeedbackInjector:
    """
    Selects the most relevant, highest-impact feedback entries for a given
    translation context and formats them for injection into the prompt.
    """

    def __init__(self, db: Optional[FeedbackDB] = None, scorer: Optional[ImpactScorer] = None):
        self._db = db or FeedbackDB()
        self._scorer = scorer or ImpactScorer()
        self._processor = FeedbackProcessor()

    def inject_to_translator_prompt(
        self,
        section_id: str,
        top_k: int = 5,
        feedback_types: Optional[list[str]] = None,
    ) -> str:
        """
        Build a prompt block with the top-k most impactful feedback examples
        relevant to *section_id*.

        Relevance is determined by section match (exact > prefix match > all),
        filtered by *feedback_types* if provided.
        """
        all_entries = self._db.all()
        if feedback_types:
            all_entries = [e for e in all_entries if e.feedback_type in feedback_types]

        # Priority: exact section match, then same section prefix, then all
        exact = [e for e in all_entries if e.section_id == section_id]
        prefix = section_id.split(".")[0]
        prefix_match = [
            e for e in all_entries
            if e.section_id != section_id and e.section_id.startswith(prefix)
        ]
        remainder = [
            e for e in all_entries
            if e not in exact and e not in prefix_match
        ]
        ordered = exact + prefix_match + remainder

        # Score and select top-k
        scored = self._scorer.score_all(ordered)
        scored.sort(key=lambda e: -e.impact_score)
        selected = scored[:top_k]

        if not selected:
            return (
                f"## Feedback Corrections (section {section_id})\n"
                "(no relevant feedback found)\n"
            )

        lines = [f"## Feedback Corrections (section {section_id}) - top {len(selected)} examples"]
        for entry in selected:
            lines.append("")
            lines.append(self._processor.to_few_shot_example(entry))
        lines.append("")
        return "\n".join(lines)
