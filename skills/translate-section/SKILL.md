---
name: translate-section
description: Translate sections from sections.json into Korean using glossary.json. Includes automatic 2-agent QA (Translator + Reviewer). Use after /build-glossary.
---

# translate-section

Translates sections from `workspace/sections.json` with inline quality assurance.

## Usage

```
/translate-section --page <N>              # All sections on page N
/translate-section --pages <N>-<M>         # Page range
/translate-section --id <section_id>       # Specific section
/translate-section --all                   # Entire document (batched)
/translate-section --type definition       # Only sections of a given type
```

**Examples:**
```
/translate-section --page 1
/translate-section --pages 1-5
/translate-section --id p003_s002
/translate-section --all
```

## Prerequisites

Both files must exist:
- `workspace/sections.json` (from `/parse-pdf`)
- `workspace/glossary.json` (from `/build-glossary`)

## 2-Agent Translation Flow

For each section, run this flow:

---

### Agent 1: Translator

You are a professional academic translator specializing in the document's domain. Your job is to produce a first-draft Korean translation.

**Inputs:**
- The English source text and block type
- The full glossary from `workspace/glossary.json`

**Rules:**
1. **Glossary compliance (non-negotiable):** Every term listed in glossary.json MUST be translated using the specified Korean term. No exceptions.

2. **Math preservation:** All math expressions — inline `$...$`, display `$$...$$`, `\[...\]`, `\(...\)` — must be copied exactly unchanged into the translation.

3. **Tone by block type:**
   - `definition`, `theorem`, `lemma`, `corollary`: Formal academic Korean. Use 정의체 ("~이다", "~한다").
   - `proof`: Step-by-step logical Korean. Use "~이므로", "~따라서", "~임을 알 수 있다".
   - `example`: Accessible, explanatory tone. Use "~해보자", "~을 생각해보자".
   - `remark`: Conversational but academic. Use "~에 주목하자", "~임을 참고하라".
   - `text`: Natural flowing Korean prose.

4. **Label translation:**
   - "Definition 1.1" → "정의 1.1"
   - "Theorem 2.3" → "정리 2.3"
   - "Lemma 4.1" → "보조정리 4.1"
   - "Corollary 3.2" → "따름정리 3.2"
   - "Proof." → "증명."
   - "Example 1." → "예시 1."
   - "Remark." → "참고."

5. **Do not add or remove content.** Translate what is there.

6. **Do not translate proper names** (author names, place names).

Output the Korean translation only.

---

### Agent 2: Reviewer

You are a senior Korean academic editor reviewing a translation. Check the draft translation against the original.

**Checklist — check each item:**

1. **용어 준수**: Are all glossary terms translated correctly? Flag any English term that should be in the glossary but was left untranslated or mistranslated.

2. **수식 보존**: Count the math blocks in the original (`$`, `$$`, `\[`, `\(`). Are the same blocks present and unchanged in the translation?

3. **문체 적합**: Does the tone match the block type? Flag any informal expressions in formal blocks or vice versa.

4. **직역 감지**: Flag awkward literal translations:
   - "~하는 것이 가능하다" → should be "~할 수 있다"
   - "~임이 증명된다" → should be "~임을 보인다" (in proofs)
   - Excessive noun stacking (과도한 명사화): "~의 ~의 ~의 ~"
   - Redundant subject repetition

5. **내용 완전성**: Is any sentence or paragraph from the original missing?

**Decision:**
- If all checks pass → output `PASS`
- If issues found → output `REVISE: <list of specific corrections>`

If `REVISE`: Apply the corrections to the translation and produce the final version.

---

## Output

Save each section to `workspace/translated/<id>.json`:

```json
{
  "id": "p001_s002",
  "page": 1,
  "type": "definition",
  "label": "정의 1.1",
  "original": "A category C consists of a collection of objects...",
  "translated": "범주 C는 대상들의 모음으로 구성되며...",
  "reviewer_status": "pass"
}
```

`reviewer_status` is one of: `"pass"` | `"revised"`

## Reporting

After each page (or batch), report:
- N sections translated
- N passed QA directly, N required revision
- List any sections that needed revision and what was fixed

If a section has unusual content (very long, mostly math, figure caption, etc.) — note it and ask if special handling is needed.

## Re-translation

To re-translate a section after editing `glossary.json`:
```
/translate-section --id p003_s002
```
This overwrites the existing `translated/p003_s002.json`.

## Next Step

After translating several pages, run `/review-batch` to check cross-section consistency.
Or when all sections are done, run `/assemble-output`.
