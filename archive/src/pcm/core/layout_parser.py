"""
Layout-Aware Parser for PCM Translation Pipeline.

Classifies text blocks extracted from PDFs (or plain text) into typed
TextBlock objects using regex + font-size heuristics.

No fitz dependency is required for parse_text(); fitz is only used
(optionally) by parse_pdf_page().
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    """A single classified text block within a document page."""

    id: str              # "block_015_001"
    block_type: str      # theorem/lemma/proof/definition/example/remark/corollary/figure/table/footnote/body
    title: str           # e.g. "Theorem 2.3 (Bolzano-Weierstrass)"
    content: str         # block text content
    page: int            # page number (0 if unknown)
    importance: str      # high/medium/low
    parent_id: Optional[str]     # for proof blocks → parent theorem id
    bbox: Optional[list]         # [x0, y0, x1, y1] or None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Block Classifier
# ---------------------------------------------------------------------------

class BlockClassifier:
    """Classifies text blocks by type using regex patterns."""

    PATTERNS = {
        "theorem":    r'^(Theorem|Thm\.?)\s*[\d.]*\s*[(\[]?',
        "lemma":      r'^(Lemma)\s*[\d.]*\s*[(\[]?',
        "corollary":  r'^(Corollary|Cor\.?)\s*[\d.]*\s*[(\[]?',
        "definition": r'^(Definition|Def\.?)\s*[\d.]*\s*[(\[]?',
        "proof":      r'^(Proof|Proof of)\b|^∎$|^□$',
        "example":    r'^(Example|Ex\.?)\s*[\d.]*\s*[(\[]?',
        "remark":     r'^(Remark|Note|Observation)\b',
        "figure":     r'^(Figure|Fig\.?)\s*[\d.]+',
        "table":      r'^(Table)\s*[\d.]+',
        "footnote":   r'^[†‡]|\[\d+\]',
    }

    IMPORTANCE = {
        "theorem":    "high",
        "lemma":      "high",
        "corollary":  "high",
        "definition": "high",
        "proof":      "medium",
        "example":    "medium",
        "remark":     "low",
        "figure":     "medium",
        "table":      "medium",
        "footnote":   "low",
        "body":       "low",
    }

    def classify(self, text: str, font_size: float = 10.0, is_bold: bool = False) -> str:
        """
        Returns block type string.

        Checks regex patterns against the first line of *text*.
        Bold + large font + no keyword → may still be a section header; we
        classify those as "body" since we don't have a "section" type here.
        """
        if not text or not text.strip():
            return "body"

        first_line = text.strip().splitlines()[0].strip()

        for block_type, pattern in self.PATTERNS.items():
            if re.match(pattern, first_line, re.IGNORECASE):
                return block_type

        # Heuristic: very small text / starts with footnote marker
        if font_size < 8.0:
            return "footnote"

        return "body"

    def extract_title(self, text: str, block_type: str) -> str:
        """
        Extracts the title/label from the first line of a block.

        For body blocks returns the first 60 characters.
        For structured blocks returns the full first line.
        """
        if not text or not text.strip():
            return ""

        first_line = text.strip().splitlines()[0].strip()

        if block_type == "body":
            # Return a short snippet as a pseudo-title
            return first_line[:60] + ("…" if len(first_line) > 60 else "")

        if block_type == "proof":
            # Proof blocks: just "Proof" or "Proof of ..."
            m = re.match(r'^(Proof(?:\s+of\s+[^.]+)?)', first_line, re.IGNORECASE)
            if m:
                return m.group(1).strip()
            return first_line[:60]

        # For labelled blocks (theorem, definition, etc.) the entire first
        # line is the title, e.g. "Theorem 2.3 (Bolzano-Weierstrass)."
        # Strip trailing punctuation.
        title = re.sub(r'[.:]$', '', first_line).strip()
        return title


# ---------------------------------------------------------------------------
# Layout-Aware Parser
# ---------------------------------------------------------------------------

class LayoutAwareParser:
    """
    Parses structured text (already extracted from PDF or plain text)
    into typed TextBlock objects.

    Usage::

        parser = LayoutAwareParser()
        blocks = parser.parse_text(raw_text, page=13)
        # → list of TextBlock

    When fitz IS available, use parse_pdf_page() for font-size-aware parsing.
    """

    def __init__(self):
        self.classifier = BlockClassifier()
        self._block_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_text(self, text: str, page: int = 0) -> List[TextBlock]:
        """
        Splits raw text into blocks by detecting section boundaries.

        Heuristic: blank line OR keyword match at the start of a line
        signals a new block boundary.
        """
        if not text or not text.strip():
            return []

        raw_segments = self._split_into_segments(text)
        blocks: List[TextBlock] = []
        last_structured_id: Optional[str] = None  # id of last theorem/lemma/definition

        for segment in raw_segments:
            segment = segment.strip()
            if not segment:
                continue

            block_type = self.classifier.classify(segment)
            title = self.classifier.extract_title(segment, block_type)
            importance = self.classifier.IMPORTANCE.get(block_type, "low")
            block_id = self._make_block_id(page)

            # Wire proof → parent theorem/lemma/definition
            parent_id: Optional[str] = None
            if block_type == "proof" and last_structured_id:
                parent_id = last_structured_id

            block = TextBlock(
                id=block_id,
                block_type=block_type,
                title=title,
                content=segment,
                page=page,
                importance=importance,
                parent_id=parent_id,
                bbox=None,
                metadata={},
            )
            blocks.append(block)

            # Track last "anchor" block so proofs can reference it
            if block_type in ("theorem", "lemma", "corollary", "definition"):
                last_structured_id = block_id

        return blocks

    def parse_pdf_page(self, page_obj, page_num: int) -> List[TextBlock]:
        """
        Uses a fitz page object for font-size-aware parsing.

        Raises ImportError if fitz is not available.
        """
        try:
            import fitz  # noqa: F401 — just to check availability
        except ImportError:
            raise ImportError(
                "fitz (PyMuPDF) required for parse_pdf_page(). "
                "Use parse_text() instead."
            )

        blocks: List[TextBlock] = []
        last_structured_id: Optional[str] = None

        # Extract blocks with font metadata via get_text("dict")
        page_dict = page_obj.get_text("dict")
        for raw_block in page_dict.get("blocks", []):
            if raw_block.get("type") != 0:
                # type 1 = image block — skip
                continue

            lines_text: list[str] = []
            font_sizes: list[float] = []
            is_bold = False

            for line in raw_block.get("lines", []):
                line_str = ""
                for span in line.get("spans", []):
                    line_str += span.get("text", "")
                    font_sizes.append(span.get("size", 10.0))
                    flags = span.get("flags", 0)
                    if flags & 16:  # bold flag in fitz
                        is_bold = True
                lines_text.append(line_str)

            full_text = "\n".join(lines_text).strip()
            if not full_text:
                continue

            avg_font = sum(font_sizes) / len(font_sizes) if font_sizes else 10.0
            block_type = self.classifier.classify(full_text, font_size=avg_font, is_bold=is_bold)
            title = self.classifier.extract_title(full_text, block_type)
            importance = self.classifier.IMPORTANCE.get(block_type, "low")
            block_id = self._make_block_id(page_num)

            bbox = raw_block.get("bbox")
            bbox_list = list(bbox) if bbox else None

            parent_id: Optional[str] = None
            if block_type == "proof" and last_structured_id:
                parent_id = last_structured_id

            block = TextBlock(
                id=block_id,
                block_type=block_type,
                title=title,
                content=full_text,
                page=page_num,
                importance=importance,
                parent_id=parent_id,
                bbox=bbox_list,
                metadata={"avg_font_size": round(avg_font, 1), "is_bold": is_bold},
            )
            blocks.append(block)

            if block_type in ("theorem", "lemma", "corollary", "definition"):
                last_structured_id = block_id

        return blocks

    def to_json(self, blocks: List[TextBlock]) -> dict:
        """Converts blocks to a serialisable schema dict."""
        return {
            "block_count": len(blocks),
            "blocks": [
                {
                    "id": b.id,
                    "block_type": b.block_type,
                    "title": b.title,
                    "content": b.content,
                    "page": b.page,
                    "importance": b.importance,
                    "parent_id": b.parent_id,
                    "bbox": b.bbox,
                    "metadata": b.metadata,
                }
                for b in blocks
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_block_id(self, page: int) -> str:
        self._block_counter += 1
        return f"block_{page:03d}_{self._block_counter:03d}"

    def _split_into_segments(self, text: str) -> List[str]:
        """
        Splits *text* into candidate block segments.

        Strategy:
        1. Split on double newlines (blank lines) first.
        2. Within each chunk, check whether a keyword pattern starts a new
           block mid-chunk (e.g. "...last sentence.\n\nTheorem 1.1.").
           If so, break there too.
        """
        # Normalise line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Primary split: blank lines
        rough_chunks = re.split(r'\n{2,}', text)

        # Secondary split: keyword at start of line inside a chunk
        keyword_re = re.compile(
            r'^(?:'
            r'Theorem|Thm\.?|Lemma|Corollary|Cor\.?|Definition|Def\.?|'
            r'Proof(?:\s+of)?|Example|Ex\.?|Remark|Note|Observation|'
            r'Figure|Fig\.?|Table'
            r')\b',
            re.MULTILINE | re.IGNORECASE,
        )

        segments: List[str] = []
        for chunk in rough_chunks:
            lines = chunk.split("\n")
            current: List[str] = []
            for line in lines:
                if current and keyword_re.match(line.strip()):
                    # Flush current segment and start a new one
                    segments.append("\n".join(current))
                    current = [line]
                else:
                    current.append(line)
            if current:
                segments.append("\n".join(current))

        return [s.strip() for s in segments if s.strip()]
