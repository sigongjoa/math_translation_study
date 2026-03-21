---
name: assemble-output
description: Combine all translated section JSON files into a final LaTeX or Markdown document. Use after translation is complete and /review-batch has been run.
---

# assemble-output

Collects all `workspace/translated/*.json` files and assembles them into a publication-ready document.

## Usage

```
/assemble-output [--format latex|markdown] [--output <path>] [--workspace <dir>] [--title <str>] [--part <str>]
```

**Examples:**
```
/assemble-output
/assemble-output --format latex --output results/chapter1.tex
/assemble-output --format markdown --output results/chapter1.md
/assemble-output --title "프린스턴 수학 안내서" --part "I"
```

Default output: `workspace/output.tex`

## Steps

1. Check that `workspace/translated/` has files. If empty, stop and say "번역된 섹션이 없습니다. /translate-section 을 먼저 실행하세요."

2. Run the builder script:
   ```bash
   python skills/assemble-output/scripts/latex_builder.py \
     --sections-dir workspace/translated \
     --glossary workspace/glossary.json \
     --output workspace/output.tex \
     [--title "..."] [--part "I"]
   ```

3. Report:
   - Number of sections assembled
   - Output file path
   - Estimated page count (rough: total Korean chars ÷ 1200)
   - Compile instructions

4. Print compile instructions:
   ```
   XeLaTeX로 컴파일:
   xelatex workspace/output.tex
   xelatex workspace/output.tex  (twice for cross-refs)
   ```

## Markdown Output

If `--format markdown` is specified, produce a Markdown file instead:

```markdown
# 1.1 범주론 소개

범주 C는 대상들의 모음으로 구성되며...

> **정의 1.1** (범주)
> 범주 C는...

**정리 1.3** 모든 범주에서...

*증명.* $f \circ g$를 고려하면...
```

Markdown is useful for quick review before committing to LaTeX.

## What the Script Produces

The LaTeX output includes:
- Full Korean XeLaTeX preamble (kotex, fontspec, amsmath, tcolorbox)
- Noto Serif/Sans CJK KR fonts
- Styled boxes for definition/theorem/example/remark blocks
- Proper math environments
- Table of contents
- Bookmarks (hyperref)

## Partial Assembly

To preview just a few sections:
```
/assemble-output --pages 1-5
```
This assembles only sections from pages 1-5.

## Next Step

Compile with XeLaTeX and review the PDF. If there are formatting issues, you can:
- Edit `workspace/translated/<id>.json` directly and re-assemble
- Fix glossary and re-translate specific sections
