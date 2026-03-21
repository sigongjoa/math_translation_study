---
name: review-batch
description: Audit all translated sections for cross-section quality issues: terminology inconsistency, missing math blocks, missing content, and untranslated English. Run after translating multiple sections before final assembly.
---

# review-batch

Audits all files in `workspace/translated/` for cross-section problems that the per-section reviewer cannot catch.

## Usage

```
/review-batch [--workspace <dir>]
```

## Steps

1. Read `workspace/glossary.json` (for term consistency checks).

2. Read ALL files in `workspace/translated/*.json`, sorted by page order.

3. Also read the corresponding original sections from `workspace/sections.json` for comparison.

4. Run the following 4 checks across all sections:

---

### Check 1: 용어 일관성 (Terminology Consistency)

For each English term in `glossary.json`, scan all translations.
Flag any section where:
- The English term appears untranslated in the Korean text
- The term is translated differently from glossary.json

Example finding:
```
⚠ "category" inconsistency:
  - p003_s002: "카테고리" (should be "범주")
  - p007_s001: "범주" ✓
```

---

### Check 2: 수식 보존 (Math Block Integrity)

For each section, count math delimiters in original vs translated:
- Count `$...$` occurrences
- Count `$$...$$` or `\[...\]` occurrences

Flag any section where counts differ:

```
⚠ Math block mismatch in p007_s003:
  Original: 5 math blocks
  Translated: 4 math blocks
```

---

### Check 3: 내용 누락 (Content Completeness)

For each section, compare paragraph count and rough word count:
- If translated word count (Korean chars × 0.5) is less than 40% of original word count, flag it
- If a section in sections.json has no corresponding file in translated/, flag it as untranslated

```
⚠ Possibly incomplete translation: p012_s001
  Original: 450 words → Expected: ~225 Korean chars minimum
  Translated: 80 chars (too short)

⚠ Untranslated section: p009_s004
```

---

### Check 4: 잔류 영어 (Residual English)

Scan translated text for sequences of 3+ consecutive English words that are not:
- Inside math blocks ($...$)
- Proper nouns (names, places)
- Technical terms expected in Korean academic text (e.g., "PDF", "LaTeX")

```
⚠ Possible untranslated content in p005_s002:
  "...범주 C에서 the composition of morphisms는..."
  → "morphisms의 합성" or "사상의 합성"
```

---

## Output: `workspace/review_report.md`

```markdown
# 번역 품질 리포트
생성일: 2026-03-21

## 요약
- 총 검토 섹션: 47
- 문제 발견: 5개 섹션
- 재번역 권장: 3개 섹션

## 용어 불일치 (2건)
- **p003_s002**: "category" → "카테고리" 사용 (glossary: "범주")
- **p011_s001**: "morphism" → "모피즘" 사용 (glossary: "사상")

## 수식 누락 의심 (1건)
- **p007_s003**: 원문 5개 수식 → 번역 4개 수식

## 번역 누락 (1건)
- **p009_s004**: 번역 파일 없음

## 잔류 영어 (1건)
- **p005_s002**: "the composition of morphisms" 미번역

## 재번역 권장 섹션
- p003_s002 (용어 불일치)
- p007_s003 (수식 누락)
- p005_s002 (잔류 영어)
```

## After the Report

Print the report summary and ask:
"재번역할 섹션이 있습니다. `/translate-section --id <id>` 로 개별 재번역하거나, 위 섹션들을 모두 재번역할까요?"

If user says yes to all: re-run `/translate-section` for each flagged section automatically.

## Next Step

After issues are resolved, run `/assemble-output` to produce the final document.
