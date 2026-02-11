#!/usr/bin/env python3
"""
Translation verifier: post-polishing quality verification for translated math sections.
4 verification modules: formula integrity, semantic equivalence, logic/facts, deep research.
Uses Ollama LLMs + rule-based checks + Wikipedia API for fact verification.
"""

import requests
import json
import re
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple

# Reuse the standard glossary from translator
from translator import MATH_GLOSSARY


class CheckResult:
    """Result of a single verification check."""
    def __init__(self, score: int = 100, issues: List[str] = None,
                 auto_fixed: List[str] = None, flagged: List[str] = None):
        self.score = max(0, min(100, score))
        self.issues = issues or []
        self.auto_fixed = auto_fixed or []
        self.flagged = flagged or []

    def to_dict(self) -> Dict:
        d = {"score": self.score, "issues": self.issues}
        if self.auto_fixed:
            d["auto_fixed"] = self.auto_fixed
        if self.flagged:
            d["flagged"] = self.flagged
        return d


class TranslationVerifier:
    """Post-polishing verification for translated mathematical text."""

    # LaTeX math patterns to extract and compare
    MATH_PATTERNS = [
        r'\$[^$]+?\$',           # inline math $...$
        r'\$\$[^$]+?\$\$',       # display math $$...$$
        r'\\\([^)]+?\\\)',        # \(...\)
        r'\\\[[^\]]+?\\\]',       # \[...\]
    ]

    # LaTeX commands that must be preserved
    LATEX_COMMANDS = [
        r'\\frac\{[^}]*\}\{[^}]*\}',
        r'\\sum',  r'\\prod',  r'\\int',
        r'\\lim',  r'\\inf',   r'\\sup',
        r'\\sqrt',  r'\\log',  r'\\ln',  r'\\exp',
        r'\\sin',  r'\\cos',   r'\\tan',
        r'\\alpha', r'\\beta',  r'\\gamma', r'\\delta',
        r'\\epsilon', r'\\zeta', r'\\eta', r'\\theta',
        r'\\lambda', r'\\mu',   r'\\nu',  r'\\pi',
        r'\\rho',  r'\\sigma',  r'\\tau',  r'\\phi',
        r'\\chi',  r'\\psi',    r'\\omega',
        r'\\Gamma', r'\\Delta', r'\\Theta', r'\\Lambda',
        r'\\Sigma', r'\\Phi',   r'\\Psi',  r'\\Omega',
        r'\\mathbb\{[A-Z]\}',
        r'\\mathcal\{[A-Z]\}',
        r'\\mathfrak\{[a-z]\}',
        r'\\text\{[^}]*\}',
        r'\\mathrm\{[^}]*\}',
        r'\\operatorname\{[^}]*\}',
        r'\\subset', r'\\supset', r'\\subseteq', r'\\supseteq',
        r'\\in', r'\\notin', r'\\cup', r'\\cap',
        r'\\times', r'\\otimes', r'\\oplus',
        r'\\to', r'\\rightarrow', r'\\leftarrow', r'\\mapsto',
        r'\\infty', r'\\partial', r'\\nabla',
        r'\\forall', r'\\exists',
        r'\\leq', r'\\geq', r'\\neq', r'\\approx', r'\\equiv',
    ]

    # Variable patterns (single letters, possibly with subscripts/superscripts)
    VAR_PATTERN = r'(?<![a-zA-Z\\])([A-Za-z])(?:_\{?[^}\s]*\}?)?(?:\^\{?[^}\s]*\}?)?'

    def __init__(self, model_name: str = "qwen2.5:14b",
                 base_url: str = "http://localhost:11434",
                 verify_types: List[str] = None,
                 research_model: str = "deepseek-r1:7b"):
        self.model_name = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
        self.research_model = research_model
        self.verify_types = verify_types or ["formula", "semantic", "logic", "research"]

        # Weights for final score
        self.weights = {
            "formula": 0.35,
            "semantic": 0.30,
            "logic": 0.20,
            "research": 0.15,
        }

    def _call_ollama(self, prompt: str, temperature: float = 0.2,
                     max_tokens: int = 2048, model: str = None) -> str:
        """Call Ollama API and return the response text."""
        use_model = model or self.model_name
        prompt_text = prompt

        # Qwen3 uses thinking tokens that count toward num_predict,
        # so we need extra budget beyond the desired output tokens
        predict_budget = max_tokens
        if "qwen3" in use_model.lower():
            predict_budget = max_tokens + 3000  # extra for thinking

        payload = {
            "model": use_model,
            "prompt": prompt_text,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": predict_budget,
                "repeat_penalty": 1.1,
                "top_k": 40,
                "top_p": 0.9,
            }
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=600)
            response.raise_for_status()
            text = response.json().get("response", "").strip()
            # Strip <think>...</think> blocks if present (Qwen3 thinking mode)
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            return text
        except requests.exceptions.RequestException as e:
            print(f"  Ollama error: {e}")
            return ""

    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """Extract JSON object from LLM response."""
        if not text:
            return None
        # Try to find JSON block
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        # Try the whole text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    # ═══════════════════════════════════════════════════════════
    # Module 1: Formula Integrity (90% rule-based, 10% LLM)
    # ═══════════════════════════════════════════════════════════

    def _extract_math_tokens(self, text: str) -> List[str]:
        """Extract all math expressions and LaTeX commands from text."""
        tokens = []

        # Extract full math regions
        for pattern in self.MATH_PATTERNS:
            for match in re.finditer(pattern, text, re.DOTALL):
                tokens.append(match.group(0))

        # Extract LaTeX commands
        for pattern in self.LATEX_COMMANDS:
            for match in re.finditer(pattern, text):
                tokens.append(match.group(0))

        # Extract standalone variables in math context
        # Only look inside math delimiters to reduce false positives
        math_regions = []
        for pattern in self.MATH_PATTERNS:
            math_regions.extend(re.findall(pattern, text, re.DOTALL))
        for region in math_regions:
            for match in re.finditer(self.VAR_PATTERN, region):
                tokens.append(match.group(0))

        return tokens

    def _check_formula_integrity(self, original: str, translated: str) -> Tuple[CheckResult, str]:
        """Check that mathematical formulas are preserved in translation.
        Returns (CheckResult, possibly_fixed_translation).
        """
        orig_tokens = self._extract_math_tokens(original)
        trans_tokens = self._extract_math_tokens(translated)

        if not orig_tokens:
            # No math in original - perfect score
            return CheckResult(score=100), translated

        orig_set = set(orig_tokens)
        trans_set = set(trans_tokens)

        missing = orig_set - trans_set
        extra = trans_set - orig_set

        issues = []
        auto_fixed = []
        fixed_text = translated

        # ── Rule-based auto-fixes ──

        # Fix 1: HTML sup/sub → LaTeX
        html_sup = re.findall(r'<sup>(.*?)</sup>', fixed_text)
        if html_sup:
            for s in html_sup:
                fixed_text = fixed_text.replace(f'<sup>{s}</sup>', f'^{{{s}}}')
            auto_fixed.append(f"Converted {len(html_sup)} HTML superscripts to LaTeX")

        html_sub = re.findall(r'<sub>(.*?)</sub>', fixed_text)
        if html_sub:
            for s in html_sub:
                fixed_text = fixed_text.replace(f'<sub>{s}</sub>', f'_{{{s}}}')
            auto_fixed.append(f"Converted {len(html_sub)} HTML subscripts to LaTeX")

        # Fix 2: Restore missing dollar-sign delimited formulas
        for token in missing.copy():
            if token.startswith('$') and token.endswith('$'):
                inner = token[1:-1] if not token.startswith('$$') else token[2:-2]
                # Check if the inner content exists without delimiters
                if inner in fixed_text and f'${inner}$' not in fixed_text:
                    fixed_text = fixed_text.replace(inner, token, 1)
                    auto_fixed.append(f"Restored math delimiters: {token[:40]}")
                    missing.discard(token)

        # Fix 3: Fix broken LaTeX commands (missing backslash)
        for cmd in ['frac', 'sum', 'prod', 'int', 'lim', 'sqrt', 'log', 'ln',
                     'sin', 'cos', 'tan', 'exp', 'infty', 'partial', 'nabla']:
            broken = re.findall(rf'(?<!\\){cmd}(?=[\s{{(])', fixed_text)
            if broken:
                fixed_text = re.sub(rf'(?<!\\)({cmd})(?=[\s{{(])', rf'\\{cmd}', fixed_text)
                auto_fixed.append(f"Restored backslash for \\{cmd}")

        # Recalculate after fixes
        fixed_tokens = set(self._extract_math_tokens(fixed_text))
        still_missing = orig_set - fixed_tokens

        # Score calculation
        if len(orig_set) == 0:
            score = 100
        else:
            preserved_ratio = 1.0 - (len(still_missing) / len(orig_set))
            score = int(preserved_ratio * 100)

        for token in still_missing:
            issues.append(f"Missing: {token[:60]}")

        # ── LLM assist for ambiguous cases (score 50-90) ──
        if 50 <= score <= 90 and "formula" in self.verify_types:
            llm_result = self._llm_formula_check(original, fixed_text, list(still_missing)[:5])
            if llm_result:
                if llm_result.get("actually_preserved"):
                    # LLM says some "missing" formulas are actually equivalent forms
                    false_positives = llm_result.get("actually_preserved", 0)
                    adjusted = len(still_missing) - false_positives
                    if adjusted >= 0:
                        preserved_ratio = 1.0 - (adjusted / len(orig_set))
                        score = int(preserved_ratio * 100)
                        issues.append(f"LLM: {false_positives} formulas in equivalent form")

        return CheckResult(score=score, issues=issues, auto_fixed=auto_fixed), fixed_text

    def _llm_formula_check(self, original: str, translated: str,
                           missing_formulas: List[str]) -> Optional[Dict]:
        """LLM-assisted check for ambiguous formula preservation."""
        missing_str = "\n".join([f"  - {f}" for f in missing_formulas])

        prompt = f"""You are a mathematical formula verification expert.
Compare the original English math text with its Korean translation.
Some formulas appear to be missing from the translation. Check if they are:
1. Actually present but in a different equivalent notation
2. Genuinely missing

Missing formulas:
{missing_str}

Original (first 1500 chars):
{original[:1500]}

Translation (first 1500 chars):
{translated[:1500]}

Respond in JSON only:
{{"actually_preserved": <number of formulas that ARE present in equivalent form>, "genuinely_missing": <number truly missing>, "notes": "<brief explanation>"}}"""

        result = self._call_ollama(prompt, temperature=0.1, max_tokens=512)
        return self._parse_json_response(result)

    # ═══════════════════════════════════════════════════════════
    # Module 2: Semantic Equivalence
    # ═══════════════════════════════════════════════════════════

    def _check_semantic_equivalence(self, original: str, translated: str,
                                     title: str = "") -> CheckResult:
        """Check semantic preservation between original and translation."""
        # Split into paragraphs for comparison
        orig_paras = [p.strip() for p in original.split('\n\n') if p.strip()]
        trans_paras = [p.strip() for p in translated.split('\n\n') if p.strip()]

        if not orig_paras or not trans_paras:
            return CheckResult(score=100)

        issues = []
        auto_fixed = []
        para_scores = []

        # Compare aligned paragraph pairs (up to 8 pairs for efficiency)
        num_pairs = min(len(orig_paras), len(trans_paras), 8)

        for i in range(num_pairs):
            orig_para = orig_paras[i][:800]
            trans_para = trans_paras[min(i, len(trans_paras) - 1)][:800]

            score_data = self._llm_semantic_score(orig_para, trans_para, i + 1)
            if score_data:
                para_score = score_data.get("score", 7)
                para_scores.append(para_score)
                if para_score < 5:
                    issues.append(
                        f"Para {i+1}: low semantic score {para_score}/10 - "
                        f"{score_data.get('reason', 'meaning may be distorted')}"
                    )
                elif para_score < 7:
                    issues.append(
                        f"Para {i+1}: moderate score {para_score}/10 - "
                        f"{score_data.get('reason', 'minor meaning shift')}"
                    )
            else:
                para_scores.append(7)  # default if LLM fails

        # Check glossary term usage
        glossary_issues = self._check_glossary_terms(original, translated)
        issues.extend(glossary_issues)

        # Calculate overall score
        if para_scores:
            avg_para = sum(para_scores) / len(para_scores)
            score = int(avg_para * 10)  # scale 1-10 → 10-100
        else:
            score = 70  # default

        # Penalize for glossary issues
        score = max(0, score - len(glossary_issues) * 3)

        # Penalize for paragraph count mismatch
        if len(orig_paras) > 0:
            ratio = len(trans_paras) / len(orig_paras)
            if ratio < 0.5 or ratio > 2.0:
                issues.append(
                    f"Paragraph count mismatch: {len(orig_paras)} orig vs {len(trans_paras)} trans"
                )
                score = max(0, score - 10)

        return CheckResult(score=score, issues=issues, auto_fixed=auto_fixed)

    def _llm_semantic_score(self, orig_para: str, trans_para: str,
                             para_num: int) -> Optional[Dict]:
        """Score semantic equivalence of a paragraph pair."""
        prompt = f"""Compare this English paragraph with its Korean translation.
Rate semantic preservation on a scale of 1-10:
- 10: Perfect meaning preservation
- 7-9: Minor omissions/additions but core meaning intact
- 4-6: Some meaning lost or distorted
- 1-3: Severely distorted or mostly wrong

English:
{orig_para}

Korean translation:
{trans_para}

Respond in JSON only:
{{"score": <1-10>, "reason": "<brief reason in English, max 20 words>"}}"""

        result = self._call_ollama(prompt, temperature=0.1, max_tokens=256)
        parsed = self._parse_json_response(result)
        if parsed and "score" in parsed:
            parsed["score"] = max(1, min(10, int(parsed["score"])))
        return parsed

    def _check_glossary_terms(self, original: str, translated: str) -> List[str]:
        """Check that standard math terms are correctly translated."""
        issues = []
        orig_lower = original.lower()

        for eng, kor in MATH_GLOSSARY.items():
            if eng.lower() in orig_lower:
                # Term exists in original; check Korean translation has the Korean term
                if kor not in translated:
                    # Could be a different valid translation - only flag major terms
                    if len(eng) > 4:  # skip very short terms like "ring", "field"
                        issues.append(f"Glossary: '{eng}' ({kor}) not found in translation")

        return issues[:5]  # limit to 5 glossary issues

    # ═══════════════════════════════════════════════════════════
    # Module 3: Logic & Facts
    # ═══════════════════════════════════════════════════════════

    def _check_logic_facts(self, original: str, translated: str,
                            title: str = "") -> CheckResult:
        """Check preservation of logical claims and factual statements."""
        issues = []
        flagged = []

        # Extract verifiable claims via LLM
        claims = self._extract_claims(original, title)
        if not claims:
            return CheckResult(score=100)

        # Verify each claim is preserved in translation
        for claim in claims[:8]:  # max 8 claims
            preservation = self._verify_claim_preserved(claim, translated)
            if preservation:
                if not preservation.get("preserved", True):
                    reason = preservation.get("reason", "claim not found in translation")
                    flagged.append(f"{claim[:80]} → {reason}")

        # Check internal logic consistency
        logic_issues = self._check_internal_logic(translated)
        issues.extend(logic_issues)

        # Score
        if not claims:
            score = 100
        else:
            preserved_count = len(claims) - len(flagged)
            score = int((preserved_count / len(claims)) * 100)

        score = max(0, score - len(logic_issues) * 5)

        return CheckResult(score=score, issues=issues, flagged=flagged)

    def _extract_claims(self, text: str, title: str = "") -> List[str]:
        """Extract verifiable factual claims from the text."""
        prompt = f"""Extract verifiable factual claims from this math text.
Focus on: theorem attributions, dates, numerical values, definitions, named results.

Title: {title}
Text (first 2000 chars):
{text[:2000]}

List up to 6 claims, one per line. Each claim should be a single clear statement.
Output ONLY the claims, one per line:"""

        result = self._call_ollama(prompt, temperature=0.1, max_tokens=512)
        if not result:
            return []

        claims = []
        for line in result.strip().split('\n'):
            line = line.strip()
            # Remove numbering
            line = re.sub(r'^\d+[\.\)]\s*', '', line)
            line = re.sub(r'^[-*]\s*', '', line)
            if line and len(line) > 15:
                claims.append(line)

        return claims[:6]

    def _verify_claim_preserved(self, claim: str, translated: str) -> Optional[Dict]:
        """Verify that a specific claim is preserved in the translation."""
        prompt = f"""Is this factual claim preserved in the Korean translation below?

Claim: {claim}

Korean translation (first 2000 chars):
{translated[:2000]}

Respond in JSON:
{{"preserved": true/false, "reason": "<brief reason>"}}"""

        result = self._call_ollama(prompt, temperature=0.1, max_tokens=256)
        return self._parse_json_response(result)

    def _check_internal_logic(self, translated: str) -> List[str]:
        """Check for internal logic issues in the translated text."""
        prompt = f"""Analyze this Korean math translation for internal logic issues.
Look for: contradictions, variable inconsistencies, broken definitions.

Text (first 2000 chars):
{translated[:2000]}

If no issues found, respond: {{"issues": []}}
If issues found, respond: {{"issues": ["issue1", "issue2"]}}
Respond in JSON only:"""

        result = self._call_ollama(prompt, temperature=0.1, max_tokens=512)
        parsed = self._parse_json_response(result)
        if parsed and "issues" in parsed:
            return [str(i) for i in parsed["issues"][:3]]
        return []

    # ═══════════════════════════════════════════════════════════
    # Module 4: Deep Research (Wikipedia fallback)
    # ═══════════════════════════════════════════════════════════

    def _check_deep_research(self, original: str, translated: str,
                              title: str = "") -> CheckResult:
        """Cross-reference claims against external sources."""
        issues = []
        flagged = []

        # Extract key claims to verify externally
        claims = self._extract_claims(original, title)
        if not claims:
            return CheckResult(score=100)

        verified = 0
        checked = 0

        for claim in claims[:5]:  # max 5 for rate limiting
            result = self._wikipedia_verify(claim)
            if result is not None:
                checked += 1
                if result["supported"]:
                    verified += 1
                else:
                    flagged.append(
                        f"Unverified: {claim[:80]} → {result.get('note', 'no Wikipedia match')}"
                    )
            time.sleep(1)  # rate limiting

        if checked == 0:
            return CheckResult(score=80, issues=["No claims could be verified externally"])

        score = int((verified / checked) * 100) if checked > 0 else 80

        return CheckResult(score=score, issues=issues, flagged=flagged)

    def _wikipedia_verify(self, claim: str) -> Optional[Dict]:
        """Verify a claim using Wikipedia MediaWiki API."""
        # Extract key search terms from the claim
        # Focus on proper nouns and technical terms
        search_terms = self._extract_search_terms(claim)
        if not search_terms:
            return None

        query = " ".join(search_terms[:4])

        try:
            # Step 1: Search Wikipedia
            search_url = "https://en.wikipedia.org/w/api.php"
            headers = {"User-Agent": "PCMTranslationVerifier/1.0 (educational project)"}
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 3,
                "format": "json",
                "utf8": 1,
            }
            resp = requests.get(search_url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            search_results = resp.json().get("query", {}).get("search", [])

            if not search_results:
                return {"supported": False, "note": "no Wikipedia results"}

            # Step 2: Get extract from top result
            page_title = search_results[0]["title"]
            extract_params = {
                "action": "query",
                "titles": page_title,
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "exsentences": 5,
                "format": "json",
                "utf8": 1,
            }
            resp2 = requests.get(search_url, params=extract_params, headers=headers, timeout=10)
            resp2.raise_for_status()
            pages = resp2.json().get("query", {}).get("pages", {})

            extract = ""
            for page in pages.values():
                extract = page.get("extract", "")
                break

            if not extract:
                return {"supported": False, "note": f"empty extract from '{page_title}'"}

            # Step 3: Use LLM to compare claim with Wikipedia extract
            supported = self._llm_fact_check(claim, extract, page_title)
            return supported

        except requests.exceptions.RequestException as e:
            return None

    def _extract_search_terms(self, claim: str) -> List[str]:
        """Extract searchable terms from a claim."""
        # Remove common words, keep nouns and proper nouns
        words = claim.split()
        stopwords = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'has', 'have', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'can', 'shall', 'that',
            'this', 'these', 'those', 'it', 'its', 'of', 'in', 'on',
            'at', 'to', 'for', 'with', 'by', 'from', 'as', 'or', 'and',
            'not', 'no', 'but', 'if', 'then', 'than', 'so', 'very',
        }

        terms = []
        for word in words:
            clean = re.sub(r'[^a-zA-Z0-9\-]', '', word)
            if clean and clean.lower() not in stopwords and len(clean) > 2:
                terms.append(clean)

        # Prioritize capitalized words (likely proper nouns)
        terms.sort(key=lambda w: (0 if w[0].isupper() else 1, -len(w)))
        return terms

    def _llm_fact_check(self, claim: str, wiki_extract: str,
                         wiki_title: str) -> Dict:
        """Use LLM to check if Wikipedia extract supports the claim."""
        prompt = f"""Does this Wikipedia extract support or contradict the claim?

Claim: {claim}

Wikipedia article: {wiki_title}
Extract: {wiki_extract[:1000]}

Respond in JSON:
{{"supported": true/false, "note": "<brief explanation>"}}"""

        result = self._call_ollama(prompt, temperature=0.1, max_tokens=256)
        parsed = self._parse_json_response(result)
        if parsed and "supported" in parsed:
            return parsed
        return {"supported": False, "note": "LLM check inconclusive"}

    # ═══════════════════════════════════════════════════════════
    # Main orchestrator
    # ═══════════════════════════════════════════════════════════

    def verify_section(self, section_data: Dict) -> Dict:
        """Run all enabled verification modules on a section.
        Returns verification report dict and may modify section_data in-place
        (auto-fixing content_translated).
        """
        original = section_data.get("content_original", "")
        translated = section_data.get("content_translated", "")
        title = section_data.get("title_original", "")

        if not original or not translated:
            return {"score": 100, "skipped": True}

        report = {}

        # Module 1: Formula integrity
        if "formula" in self.verify_types:
            print(f"    [1/4] Checking formula integrity...")
            formula_result, fixed_text = self._check_formula_integrity(original, translated)
            report["formula"] = formula_result.to_dict()
            if fixed_text != translated:
                section_data["content_translated"] = fixed_text
                translated = fixed_text  # use fixed text for subsequent checks
            time.sleep(0.3)
        else:
            report["formula"] = {"score": 100, "issues": [], "skipped": True}

        # Module 2: Semantic equivalence
        if "semantic" in self.verify_types:
            print(f"    [2/4] Checking semantic equivalence...")
            semantic_result = self._check_semantic_equivalence(original, translated, title)
            report["semantic"] = semantic_result.to_dict()
            time.sleep(0.3)
        else:
            report["semantic"] = {"score": 100, "issues": [], "skipped": True}

        # Module 3: Logic & facts
        if "logic" in self.verify_types:
            print(f"    [3/4] Checking logic and facts...")
            logic_result = self._check_logic_facts(original, translated, title)
            report["logic"] = logic_result.to_dict()
            time.sleep(0.3)
        else:
            report["logic"] = {"score": 100, "issues": [], "skipped": True}

        # Module 4: Deep research
        if "research" in self.verify_types:
            print(f"    [4/4] Cross-referencing with external sources...")
            research_result = self._check_deep_research(original, translated, title)
            report["research"] = research_result.to_dict()
        else:
            report["research"] = {"score": 100, "issues": [], "skipped": True}

        # Calculate weighted overall score
        total_score = 0
        total_weight = 0
        for module, weight in self.weights.items():
            if module in report and not report[module].get("skipped"):
                total_score += report[module]["score"] * weight
                total_weight += weight

        if total_weight > 0:
            report["score"] = int(total_score / total_weight)
        else:
            report["score"] = 100

        return report

    # ═══════════════════════════════════════════════════════════
    # Deep Research Enrichment (educational content generation)
    # ═══════════════════════════════════════════════════════════

    def enrich_section(self, section_data: Dict) -> List[Dict]:
        """Research key concepts in the section and generate educational notes.
        Returns a list of enrichment entries, each with:
          - term: the concept/person/theorem name
          - title_ko: Korean title for display
          - explanation: Korean explanation (2-4 sentences)
          - context: why it matters in this section
          - source: Wikipedia article title
        """
        original = section_data.get("content_original", "")
        title = section_data.get("title_original", "")

        if not original or len(original) < 100:
            return []

        # Step 1: Extract key concepts that need explanation
        concepts = self._extract_key_concepts(original, title)
        if not concepts:
            return []

        enrichments = []
        for concept in concepts[:6]:  # max 6 per section
            print(f"      Researching: {concept}...")
            entry = self._research_concept(concept, original)
            if entry:
                enrichments.append(entry)
            time.sleep(1)  # rate limiting

        return enrichments

    def _extract_key_concepts(self, text: str, title: str = "") -> List[str]:
        """Extract key mathematical concepts, people, and theorems that would
        benefit from additional explanation for a general reader."""
        prompt = f"""You are analyzing a mathematics textbook section for educational enrichment.
Extract key concepts that a first-time reader would need explained.

Focus on:
1. Mathematical concepts/objects (e.g., "Leech Lattice", "Monster group", "modular form")
2. Mathematicians mentioned (e.g., "Ramanujan", "Euler", "Gauss")
3. Named theorems/results (e.g., "Fermat's Last Theorem", "Euler's formula")
4. Technical terms that aren't self-explanatory (e.g., "homeomorphism", "compact manifold")

Do NOT include:
- Basic terms (number, function, set, proof)
- Terms that are self-explanatory from context

Section title: {title}
Text (first 2500 chars):
{text[:2500]}

List the most important 4-8 concepts, one per line.
Output ONLY the concept names, nothing else:"""

        result = self._call_ollama(prompt, temperature=0.2, max_tokens=512)
        if not result:
            return []

        concepts = []
        for line in result.strip().split('\n'):
            line = line.strip()
            line = re.sub(r'^\d+[\.\)]\s*', '', line)
            line = re.sub(r'^[-*]\s*', '', line)
            line = line.strip('"\'')
            if line and len(line) > 2 and len(line) < 80:
                concepts.append(line)

        return concepts[:8]

    def _research_concept(self, concept: str, section_text: str) -> Optional[Dict]:
        """Research a concept via Wikipedia and generate an educational explanation."""
        # Step 1: Get Wikipedia info
        wiki_info = self._fetch_wikipedia_summary(concept)
        if not wiki_info:
            # Try with broader search
            wiki_info = self._fetch_wikipedia_summary(concept + " mathematics")

        if not wiki_info:
            return None

        wiki_title = wiki_info["title"]
        wiki_extract = wiki_info["extract"]

        # Step 2: Generate Korean educational explanation using LLM
        prompt = f"""You are creating an educational note for a Korean reader studying mathematics.
Write a clear, accessible explanation of "{concept}" based on the Wikipedia information below.

Wikipedia article: {wiki_title}
Wikipedia extract:
{wiki_extract[:1500]}

Section context (where this concept appears):
{section_text[:500]}

Write in Korean. Your explanation should include:
1. 이 개념이 무엇인지 (1-2문장, 쉬운 말로)
2. 왜 중요한지 / 어디에 쓰이는지 (1문장)
3. 이 섹션과의 관련성 (1문장)

규칙:
- 한국어로만 작성
- 수학 기호는 LaTeX 형식 유지 ($...$)
- 총 3-5문장, 간결하게
- 비유나 직관적 설명 포함
- 설명문만 출력 (제목이나 번호 없이)

설명:"""

        explanation = self._call_ollama(prompt, temperature=0.3, max_tokens=512)
        if not explanation or len(explanation) < 30:
            return None

        # Clean the explanation
        explanation = re.sub(r'(Here is|Below is|다음은|아래는).*?\n', '', explanation)
        explanation = explanation.strip()

        # Step 3: Generate Korean title
        title_prompt = f"""Translate this mathematical concept name to Korean (with original in parentheses).
Format: "Korean Name (Original Name)"
If it's a person's name, use Korean transliteration.

Concept: {concept}

Korean title (one line only):"""

        title_ko = self._call_ollama(title_prompt, temperature=0.1, max_tokens=64)
        title_ko = title_ko.strip().split('\n')[0].strip('"\'')
        if not title_ko or len(title_ko) < 2:
            title_ko = concept

        return {
            "term": concept,
            "title_ko": title_ko,
            "explanation": explanation,
            "source": wiki_title,
        }

    def _fetch_wikipedia_summary(self, query: str) -> Optional[Dict]:
        """Fetch Wikipedia summary for a concept."""
        try:
            search_url = "https://en.wikipedia.org/w/api.php"
            headers = {"User-Agent": "PCMTranslationVerifier/1.0 (educational project)"}

            # Search
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 3,
                "format": "json",
                "utf8": 1,
            }
            resp = requests.get(search_url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("query", {}).get("search", [])

            if not results:
                return None

            # Get extract from best result
            page_title = results[0]["title"]
            extract_params = {
                "action": "query",
                "titles": page_title,
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "exsentences": 8,
                "format": "json",
                "utf8": 1,
            }
            resp2 = requests.get(search_url, params=extract_params, headers=headers, timeout=10)
            resp2.raise_for_status()
            pages = resp2.json().get("query", {}).get("pages", {})

            for page in pages.values():
                extract = page.get("extract", "")
                if extract and len(extract) > 50:
                    return {"title": page_title, "extract": extract}

            return None
        except requests.exceptions.RequestException:
            return None

    def test_connection(self) -> bool:
        """Test if the verification model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]

            if self.model_name in model_names:
                print(f"Verify model '{self.model_name}' is available")
                return True
            else:
                print(f"Verify model '{self.model_name}' not found.")
                print(f"Available: {', '.join(model_names[:5])}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Cannot connect to Ollama: {e}")
            return False


def main():
    """Test the verifier with sample data."""
    verifier = TranslationVerifier()

    if not verifier.test_connection():
        print("Please ensure Ollama is running with qwen2.5:14b")
        print("Falling back to connection test only.")
        return

    # Test with sample section
    test_section = {
        "section_id": "test",
        "title_original": "Weakening Hypotheses and Strengthening Conclusions",
        "title_translated": "가설 약화 및 결론 강화",
        "content_original": (
            "The number 1729 is famous for being expressible as the sum of two cubes "
            "in two different ways: $1729 = 1^3 + 12^3 = 9^3 + 10^3$. "
            "This was noted by Ramanujan when Hardy visited him."
        ),
        "content_translated": (
            "숫자 1729는 두 가지 다른 방식으로 세제곱의 합으로 나타낼 수 있다는 점에서 유명합니다: "
            "$1729 = 1^3 + 12^3 = 9^3 + 10^3$. "
            "이것은 하디가 라마누잔을 방문했을 때 라마누잔이 언급한 것입니다."
        ),
    }

    print("\nVerifying test section...")
    report = verifier.verify_section(test_section)
    print(f"\nVerification Report:")
    print(f"  Overall score: {report['score']}")
    for module in ["formula", "semantic", "logic", "research"]:
        if module in report:
            mod = report[module]
            print(f"  {module}: {mod['score']} "
                  f"({len(mod.get('issues', []))} issues, "
                  f"{len(mod.get('flagged', []))} flagged)")


if __name__ == "__main__":
    main()
