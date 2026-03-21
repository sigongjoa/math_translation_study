"""
Knowledge Manager: Thread-safe management of the Global Terminology Bank.

Supports the new term_bank.json schema with per-term domain translations,
usage tracking, conflict detection, and prompt injection.
"""

import json
import threading
from pathlib import Path
from typing import Optional


DEFAULT_BANK_PATH = Path(__file__).parent.parent / "data" / "term_bank.json"


class KnowledgeManager:
    """
    Thread-safe manager for the Global Terminology Bank (term_bank.json).

    The bank schema stores each term with a translations dict keyed by domain,
    allowing context-sensitive lookups and conflict detection.
    """

    def __init__(self, bank_path: Optional[str] = None):
        if bank_path is None:
            self.bank_path = DEFAULT_BANK_PATH
        else:
            self.bank_path = Path(bank_path)
        self.bank_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self._load_bank()

    # ------------------------------------------------------------------
    # Internal I/O helpers
    # ------------------------------------------------------------------

    def _load_bank(self):
        """Load the term bank from disk, initialising a blank bank if absent."""
        with self.lock:
            if self.bank_path.exists():
                with open(self.bank_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Support both the legacy schema {"terminology": ...} and the
                # new schema {"term_bank": ..., "metadata": ...}
                if "term_bank" in data:
                    self._bank = data["term_bank"]
                    self._metadata = data.get("metadata", {})
                else:
                    # Migrate legacy format: terminology[domain][term] -> translation
                    self._bank = {}
                    self._metadata = {}
                    for domain, terms in data.get("terminology", {}).items():
                        for term, translation in terms.items():
                            if term not in self._bank:
                                self._bank[term] = {
                                    "translations": {},
                                    "definition": "",
                                    "first_seen": "",
                                    "usage_count": 0,
                                    "confirmed_by": "legacy_import",
                                }
                            self._bank[term]["translations"][domain] = translation
            else:
                self._bank = {}
                self._metadata = {
                    "created_at": "2026-03-10",
                    "book": "Princeton Companion to Mathematics",
                    "last_updated": "2026-03-10",
                    "total_terms": 0,
                }
                self._save_unlocked()

    def _save_unlocked(self):
        """Persist the bank to disk. Must be called while the lock is held."""
        self._metadata["total_terms"] = len(self._bank)
        payload = {
            "term_bank": self._bank,
            "metadata": self._metadata,
        }
        with open(self.bank_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, term: str, domain: str = "general") -> Optional[str]:
        """
        Return the Korean translation of *term* in *domain*.

        Falls back to the "general" translation when the specific domain
        translation is absent.  Returns None if the term is unknown.
        """
        with self.lock:
            entry = self._bank.get(term)
            if entry is None:
                return None
            translations = entry.get("translations", {})
            result = translations.get(domain) or translations.get("general")
            if result is not None:
                entry["usage_count"] = entry.get("usage_count", 0) + 1
            return result

    def register(
        self,
        term: str,
        translation: str,
        domain: str = "general",
        section_id: Optional[str] = None,
    ) -> None:
        """
        Add or update the translation of *term* for *domain*.

        Creates a new bank entry when the term is not yet known.
        Increments usage_count on each call.
        """
        with self.lock:
            if term not in self._bank:
                self._bank[term] = {
                    "translations": {},
                    "definition": "",
                    "first_seen": section_id or "",
                    "usage_count": 0,
                    "confirmed_by": "runtime",
                }
            entry = self._bank[term]
            entry["translations"][domain] = translation
            entry["usage_count"] = entry.get("usage_count", 0) + 1
            if section_id and not entry.get("first_seen"):
                entry["first_seen"] = section_id
            self._save_unlocked()

    def get_all_for_domain(self, domain: str) -> dict:
        """Return a mapping of term -> translation for all terms in *domain*."""
        with self.lock:
            result = {}
            for term, entry in self._bank.items():
                translation = entry.get("translations", {}).get(domain)
                if translation:
                    result[term] = translation
            return result

    def inject_to_prompt(self, domain: str, top_k: int = 20) -> str:
        """
        Build a formatted string of the top-k most-used terms for *domain*,
        suitable for prepending to a translation prompt.

        Returns a string of the form:
            ## Terminology Bank ({domain}) - top {k} terms
            - field → 체(體)
            - ring → 환(環)
            ...
        """
        with self.lock:
            domain_terms = []
            for term, entry in self._bank.items():
                translation = entry.get("translations", {}).get(domain)
                if translation:
                    domain_terms.append(
                        (term, translation, entry.get("usage_count", 0))
                    )
            # Sort by usage_count descending, then alphabetically for stability
            domain_terms.sort(key=lambda x: (-x[2], x[0]))
            selected = domain_terms[:top_k]

        if not selected:
            return f"## Terminology Bank ({domain})\n(no terms registered for this domain)\n"

        lines = [f"## Terminology Bank ({domain}) - top {len(selected)} terms"]
        for term, translation, _ in selected:
            lines.append(f"  - {term} → {translation}")
        lines.append("")
        return "\n".join(lines)

    def detect_conflicts(self) -> list:
        """
        Return a list of terms that have more than one distinct translation
        across all domains (excluding 'general').

        Each item in the returned list is a dict:
            {
                "term": str,
                "translations": {domain: translation, ...},
                "conflict": True
            }
        """
        conflicts = []
        with self.lock:
            for term, entry in self._bank.items():
                translations = entry.get("translations", {})
                non_general = {
                    d: t for d, t in translations.items() if d != "general"
                }
                distinct_translations = set(non_general.values())
                if len(distinct_translations) > 1:
                    conflicts.append(
                        {
                            "term": term,
                            "translations": translations,
                            "conflict": True,
                        }
                    )
        return conflicts

    def get_stats(self) -> dict:
        """
        Return a summary dict with:
            - total_terms: int
            - domain_breakdown: {domain: count}
            - conflict_count: int
            - most_used: list of (term, usage_count) top-10
        """
        with self.lock:
            domain_counts: dict = {}
            usage_list = []
            for term, entry in self._bank.items():
                translations = entry.get("translations", {})
                for domain in translations:
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1
                usage_list.append((term, entry.get("usage_count", 0)))

        usage_list.sort(key=lambda x: -x[1])
        conflicts = self.detect_conflicts()

        return {
            "total_terms": len(self._bank),
            "domain_breakdown": domain_counts,
            "conflict_count": len(conflicts),
            "most_used": usage_list[:10],
        }


if __name__ == "__main__":
    km = KnowledgeManager()
    print("Stats:", km.get_stats())
    print("\nAlgebra injection (top 5):")
    print(km.inject_to_prompt("algebra", top_k=5))
    print("Conflicts:", len(km.detect_conflicts()))
