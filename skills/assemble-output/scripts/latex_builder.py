#!/usr/bin/env python3
"""
latex_builder.py — Assemble translated section JSON files into a LaTeX document.

Input:  workspace/translated/*.json  (one file per section)
Input:  workspace/glossary.json       (optional, for glossary appendix)
Output: workspace/output.tex          (XeLaTeX-ready Korean document)
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Text cleaning
# ─────────────────────────────────────────────────────────────────────────────

def clean_for_latex(text: str) -> str:
    """Convert translated text to proper LaTeX."""
    if not text:
        return ""

    # Markdown → LaTeX
    text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\\textit{\1}', text)
    text = _wrap_bullet_lists(text)
    text = re.sub(r'^\s*#{1,3}\s+(.+)$', r'\\paragraph{\1}', text, flags=re.MULTILINE)

    # HTML → LaTeX
    text = re.sub(r'<sup>(.*?)</sup>', r'\\textsuperscript{\1}', text)
    text = re.sub(r'<sub>(.*?)</sub>', r'\\textsubscript{\1}', text)
    text = re.sub(r'<br\s*/?>', r'\\\\', text)
    text = re.sub(r'<[^>]+>', '', text)

    # $$ ... $$ → \[ ... \]
    text = re.sub(r'\$\$(.+?)\$\$', r'\\[\1\\]', text, flags=re.DOTALL)

    # Wrap bare math-like patterns
    text = _wrap_bare_math(text)

    # Escape special chars (outside math)
    text = _escape_outside_math(text)

    # CJK ↔ Latin spacing
    text = _insert_cjk_breaks(text)

    # Clean up
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)

    return text.strip()


def _wrap_bare_math(text: str) -> str:
    math_pattern = r'(\$[^$]+?\$|\\\(.+?\\\)|\\\[.+?\\\])'
    parts = re.split(math_pattern, text, flags=re.DOTALL)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            result.append(part)
        else:
            part = re.sub(
                r'(?<!\$)(?<![\\a-zA-Z])([a-zA-Z][a-zA-Z0-9]*)([_^])(\{[^}]+\}|[a-zA-Z0-9]+)(?!\$)',
                r'$\1\2\3$', part
            )
            part = re.sub(
                r'(?<!\$)([a-zA-Z0-9])[\^][\(]([^)]+)[\)]',
                r'$\1^{\2}$', part
            )
            result.append(part)
    return ''.join(result)


def _insert_cjk_breaks(text: str) -> str:
    CJK = r'[\uac00-\ud7af\u4e00-\u9fff\u3400-\u4dbf]'
    LATIN = r'[a-zA-Z0-9]'
    text = re.sub(f'({CJK})({LATIN})', r'\1 \2', text)
    text = re.sub(f'({LATIN})({CJK})', r'\1 \2', text)
    ZWSP = r'\hspace{0pt}'

    def _break_long_cjk(match):
        run = match.group(0)
        if len(run) <= 12:
            return run
        parts = [run[i:i+10] for i in range(0, len(run), 10)]
        return ZWSP.join(parts)

    text = re.sub(f'[{chr(0xac00)}-{chr(0xd7af)}]{{10,}}', _break_long_cjk, text)
    text = re.sub(r'  +', ' ', text)
    return text


def _wrap_bullet_lists(text: str) -> str:
    lines = text.split('\n')
    result = []
    in_list = False
    for line in lines:
        is_bullet = bool(re.match(r'^\s*[*\-]\s+', line))
        if is_bullet:
            if not in_list:
                result.append('\\begin{itemize}')
                in_list = True
            result.append('\\item ' + re.sub(r'^\s*[*\-]\s+', '', line))
        else:
            if in_list:
                result.append('\\end{itemize}')
                in_list = False
            result.append(line)
    if in_list:
        result.append('\\end{itemize}')
    return '\n'.join(result)


def _escape_outside_math(text: str) -> str:
    pattern = r'(\$[^$]+\$|\\\(.+?\\\)|\\\[.+?\\\])'
    parts = re.split(pattern, text, flags=re.DOTALL)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            result.append(part)
        else:
            result.append(_safe_escape(part))
    return ''.join(result)


def _safe_escape(text: str) -> str:
    protected = {}
    counter = [0]

    def protect(match):
        key = f"@@PROT{counter[0]}@@"
        protected[key] = match.group(0)
        counter[0] += 1
        return key

    text = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', protect, text)
    text = re.sub(r'\\\\', protect, text)
    text = re.sub(r'\\item\b', protect, text)
    text = re.sub(r'\\paragraph\{[^}]*\}', protect, text)
    text = re.sub(r'\\begin\{[^}]+\}', protect, text)
    text = re.sub(r'\\end\{[^}]+\}', protect, text)

    text = text.replace('&', '\\&')
    text = text.replace('%', '\\%')
    text = text.replace('#', '\\#')
    text = text.replace('_', '\\_')
    text = text.replace('^', '\\^{}')

    for key, val in protected.items():
        text = text.replace(key, val)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Section rendering
# ─────────────────────────────────────────────────────────────────────────────

# Maps block type → tcolorbox environment name
BLOCK_BOX = {
    "definition": "definitionbox",
    "theorem":    "definitionbox",
    "lemma":      "definitionbox",
    "corollary":  "definitionbox",
    "example":    "examplebox",
    "remark":     "remarkbox",
    "proof":      None,  # no box, just italic
}


def _render_figures(figures: List[Dict]) -> str:
    """Render a list of figures as LaTeX figure environments."""
    parts = []
    for fig in figures:
        file_path = fig.get("file") or ""
        if not file_path:
            # Image not available — insert commented placeholder
            fig_id = fig.get("id", "?")
            cap = fig.get("caption", "")
            parts.append(f"% [IMAGE UNAVAILABLE: {fig_id} — {cap}]")
            continue
        # Use caption_ko if available, else fall back to English caption
        caption = fig.get("caption_ko") or fig.get("caption", "")
        caption_tex = clean_for_latex(caption) if caption else ""
        label = fig.get("id", "")

        # Path for \includegraphics (relative to CWD when running xelatex)
        # sections.json stores "workspace/images/foo.png"
        # xelatex is run from project root, so use the path as-is
        img_path = file_path

        lines = [
            r"\begin{figure}[htbp]",
            r"  \centering",
            f"  \\includegraphics[width=0.85\\textwidth]{{{img_path}}}",
        ]
        if caption_tex:
            lines.append(f"  \\caption{{{caption_tex}}}")
        if label:
            lines.append(f"  \\label{{fig:{label}}}")
        lines.append(r"\end{figure}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _render_section(data: Dict, heading_tracker: Dict) -> str:
    """Render one translated section as LaTeX."""
    btype     = data.get("type", "text")
    label_ko  = data.get("label", "")
    translated = data.get("translated", "")
    sec_id    = data.get("id", "unknown")
    figures   = data.get("figures", [])

    if not translated:
        return f"\n% [MISSING TRANSLATION: {sec_id}]\n"

    body = clean_for_latex(translated)
    fig_tex = _render_figures(figures) if figures else ""

    # Section / subsection headings
    if btype == "section":
        heading_tracker["section"] += 1
        heading_tracker["subsection"] = 0
        result = f"\n\\section{{{body}}}\n\\label{{sec:{sec_id}}}\n"
        if fig_tex:
            result += "\n" + fig_tex + "\n"
        return result

    if btype == "subsection":
        heading_tracker["subsection"] += 1
        result = f"\n\\subsection{{{body}}}\n\\label{{subsec:{sec_id}}}\n"
        if fig_tex:
            result += "\n" + fig_tex + "\n"
        return result

    # Proof (no box, use QED)
    if btype == "proof":
        label_tex = clean_for_latex(label_ko) if label_ko else "증명"
        result = f"\n\\begin{{proof}}[{label_tex}]\n{body}\n\\end{{proof}}\n"
        if fig_tex:
            result += "\n" + fig_tex + "\n"
        return result

    # Boxed blocks (definition, theorem, example, remark)
    box_env = BLOCK_BOX.get(btype)
    if box_env:
        label_tex = clean_for_latex(label_ko) if label_ko else ""
        opt = f"[{label_tex}]" if label_tex else ""
        result = f"\n\\begin{{{box_env}}}{opt}\n{body}\n\\end{{{box_env}}}\n"
        if fig_tex:
            result += "\n" + fig_tex + "\n"
        return result

    # Regular text — figures appear after paragraph
    if fig_tex:
        return f"\n{body}\n\n{fig_tex}\n"
    return f"\n{body}\n"


# ─────────────────────────────────────────────────────────────────────────────
# LaTeX preamble
# ─────────────────────────────────────────────────────────────────────────────

def generate_preamble(title: str = "번역본", author: str = "") -> str:
    author_line = f"\\author{{{author}}}\n" if author else ""
    return rf"""\documentclass[10.5pt, a4paper, twoside, openany]{{book}}

% ─── 여백 ───
\usepackage[
  top=25mm, bottom=20mm,
  inner=30mm, outer=25mm,
  bindingoffset=5mm,
  headheight=14pt, headsep=12pt
]{{geometry}}

% ─── 한글 ───
\usepackage{{kotex}}
\usepackage{{fontspec}}

% ─── 폰트 ───
\setmainfont{{Noto Serif CJK KR}}[
  UprightFont={{Noto Serif CJK KR}},
  BoldFont={{Noto Serif CJK KR Bold}},
  Ligatures=TeX,
]
\setsansfont{{Noto Sans CJK KR}}[
  UprightFont={{Noto Sans CJK KR}},
  BoldFont={{Noto Sans CJK KR Bold}},
  Ligatures=TeX,
]
\setmonofont{{Noto Sans Mono CJK KR}}[Scale=0.85]

% ─── 수식 ───
\usepackage{{amsmath, amssymb, amsthm}}

% ─── 그래픽 ───
\usepackage{{graphicx}}
\usepackage{{tikz}}
\usetikzlibrary{{arrows.meta, positioning, shapes, calc, decorations.pathreplacing}}

% ─── 한글 줄바꿈 ───
\XeTeXlinebreaklocale "ko"
\XeTeXlinebreakskip 0pt plus 3pt
\emergencystretch 5em
\tolerance=2000
\hyphenpenalty=50
\exhyphenpenalty=50
\setlength{{\hfuzz}}{{2pt}}

% ─── 행간 / 단락 ───
\linespread{{1.52}}
\setlength{{\parindent}}{{1em}}
\setlength{{\parskip}}{{0pt}}

% ─── 헤더/푸터 ───
\usepackage{{fancyhdr}}
\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[LE]{{\small\sffamily\leftmark \hfill \thepage}}
\fancyhead[RO]{{\small\sffamily\thepage \hfill \rightmark}}
\renewcommand{{\headrulewidth}}{{0.4pt}}
\fancypagestyle{{plain}}{{\fancyhf{{}}\fancyfoot[C]{{\small\thepage}}\renewcommand{{\headrulewidth}}{{0pt}}}}

% ─── 제목 스타일 ───
\usepackage{{titlesec}}
\titleformat{{\chapter}}[hang]{{\sffamily\bfseries\LARGE}}{{\thechapter}}{{12pt}}{{}}[\vspace{{2pt}}{{\titlerule[0.8pt]}}]
\titlespacing*{{\chapter}}{{0pt}}{{-10pt}}{{24pt}}
\titleformat{{\section}}[hang]{{\sffamily\bfseries\Large}}{{\thesection}}{{8pt}}{{}}
\titlespacing*{{\section}}{{0pt}}{{20pt}}{{8pt}}
\titleformat{{\subsection}}[hang]{{\sffamily\bfseries\normalsize}}{{\thesubsection}}{{6pt}}{{}}
\titlespacing*{{\subsection}}{{0pt}}{{14pt}}{{6pt}}

% ─── 박스 ───
\usepackage[most]{{tcolorbox}}

\newtcolorbox{{definitionbox}}[1][]{{
  colback=white, colframe=black,
  fonttitle=\sffamily\bfseries, title={{#1}},
  breakable, sharp corners, boxrule=0.5pt,
  left=8pt, right=8pt, top=6pt, bottom=6pt
}}
\newtcolorbox{{examplebox}}[1][]{{
  colback=white, colframe=black,
  fonttitle=\sffamily\bfseries, title={{#1}},
  breakable, sharp corners, boxrule=0.4pt,
  left=8pt, right=8pt, top=6pt, bottom=6pt
}}
\newtcolorbox{{remarkbox}}[1][]{{
  colback=white, colframe=black!60,
  fonttitle=\sffamily\bfseries, title={{#1}},
  breakable, sharp corners, boxrule=0.3pt,
  left=8pt, right=8pt, top=4pt, bottom=4pt
}}

% ─── 증명 ───
\renewcommand{{\qedsymbol}}{{$\blacksquare$}}

% ─── 교차참조 ───
\usepackage{{hyperref}}
\hypersetup{{colorlinks=false, pdfborder={{0 0 0}}, bookmarksnumbered=true}}

% ─── 목차 ───
\setcounter{{tocdepth}}{{2}}

% ─── 열거 ───
\usepackage{{enumitem}}

\title{{{title}}}
{author_line}"""


# ─────────────────────────────────────────────────────────────────────────────
# Document assembly
# ─────────────────────────────────────────────────────────────────────────────

def _sort_key(path: Path):
    """Sort section files by page then sequence number."""
    m = re.search(r'p(\d+)_s(\d+)', path.stem)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (999999, 0)


def generate_full_document(
    sections_dir: str,
    output_tex: str,
    glossary_path: Optional[str] = None,
    title: str = "번역본",
    author: str = "",
    part_label: str = "",
    pages: Optional[str] = None,
) -> None:
    sections_path = Path(sections_dir)
    json_files = sorted(sections_path.glob("*.json"), key=_sort_key)

    if not json_files:
        print(f"No JSON files in {sections_dir}", file=sys.stderr)
        sys.exit(1)

    # Filter by page range if specified
    if pages:
        parts = pages.split("-")
        p_start = int(parts[0])
        p_end = int(parts[1]) if len(parts) == 2 else p_start
        filtered = []
        for jf in json_files:
            m = re.search(r'p(\d+)', jf.stem)
            if m and p_start <= int(m.group(1)) <= p_end:
                filtered.append(jf)
        json_files = filtered

    sections = []
    for jf in json_files:
        with open(jf, encoding="utf-8") as f:
            try:
                sections.append(json.load(f))
            except json.JSONDecodeError as e:
                print(f"Warning: skipping {jf.name}: {e}", file=sys.stderr)

    print(f"Assembling {len(sections)} sections...")

    preamble = generate_preamble(title=title, author=author)
    body_parts = [r"\begin{document}", r"\maketitle", r"\tableofcontents", r"\newpage", ""]

    if part_label:
        body_parts.append(f"\\part{{{part_label}}}\n")

    heading_tracker = {"section": 0, "subsection": 0}
    for sec in sections:
        body_parts.append(_render_section(sec, heading_tracker))

    # Optional glossary appendix
    if glossary_path:
        gpath = Path(glossary_path)
        if gpath.exists():
            with open(gpath, encoding="utf-8") as f:
                glossary = json.load(f)
            terms = glossary.get("terms", {})
            if terms:
                rows = "\\\\\n".join(
                    f"\\textbf{{{eng}}} & {info.get('ko', '')} & "
                    f"{{\\small {info.get('note', '')}}}"
                    for eng, info in sorted(terms.items())
                )
                body_parts.append(r"""
\appendix
\chapter{용어 대조표}
\begin{tabular}{lll}
\textbf{English} & \textbf{한국어} & \textbf{비고} \\
\hline
""" + rows + r"""
\end{tabular}
""")

    body_parts.append(r"\end{document}")

    full_doc = preamble + "\n".join(body_parts)

    out_path = Path(output_tex)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_doc)

    print(f"LaTeX document → {out_path}")
    total_chars = sum(len(s.get("translated", "")) for s in sections)
    est_pages = max(1, total_chars // 1200)
    print(f"Estimated pages: ~{est_pages}")
    print(f"\nCompile with:")
    print(f"  xelatex {out_path}")
    print(f"  xelatex {out_path}  # run twice for ToC")


def generate_markdown(sections_dir: str, output_md: str, pages: Optional[str] = None) -> None:
    """Alternative Markdown output for quick review."""
    sections_path = Path(sections_dir)
    json_files = sorted(sections_path.glob("*.json"), key=_sort_key)

    if pages:
        parts = pages.split("-")
        p_start = int(parts[0])
        p_end = int(parts[1]) if len(parts) == 2 else p_start
        json_files = [
            jf for jf in json_files
            if (m := re.search(r'p(\d+)', jf.stem)) and p_start <= int(m.group(1)) <= p_end
        ]

    lines = []
    for jf in sorted(json_files, key=_sort_key):
        with open(jf, encoding="utf-8") as f:
            try:
                sec = json.load(f)
            except json.JSONDecodeError:
                continue

        btype = sec.get("type", "text")
        label = sec.get("label", "")
        text  = sec.get("translated", "")

        if btype == "section":
            lines.append(f"\n## {text}\n")
        elif btype == "subsection":
            lines.append(f"\n### {text}\n")
        elif btype in ("definition", "theorem", "lemma", "corollary"):
            heading = f"**{label}**" if label else f"**{btype.capitalize()}**"
            lines.append(f"\n> {heading}  \n> {text}\n")
        elif btype == "proof":
            lines.append(f"\n*증명.* {text} $\\blacksquare$\n")
        elif btype == "example":
            heading = f"**{label}**" if label else "**예시**"
            lines.append(f"\n{heading}\n\n{text}\n")
        elif btype == "remark":
            lines.append(f"\n> *참고.* {text}\n")
        else:
            lines.append(f"\n{text}\n")

    out_path = Path(output_md)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Markdown → {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Assemble translated sections into LaTeX or Markdown")
    parser.add_argument("--sections-dir", default="workspace/translated")
    parser.add_argument("--glossary", default=None)
    parser.add_argument("--output", default="workspace/output.tex")
    parser.add_argument("--format", choices=["latex", "markdown"], default="latex")
    parser.add_argument("--title", default="번역본")
    parser.add_argument("--author", default="")
    parser.add_argument("--part", default="")
    parser.add_argument("--pages", default=None, help="Only include pages N-M")
    args = parser.parse_args()

    if args.format == "markdown":
        md_out = args.output.replace(".tex", ".md") if args.output.endswith(".tex") else args.output
        generate_markdown(args.sections_dir, md_out, pages=args.pages)
    else:
        generate_full_document(
            sections_dir=args.sections_dir,
            output_tex=args.output,
            glossary_path=args.glossary,
            title=args.title,
            author=args.author,
            part_label=args.part,
            pages=args.pages,
        )


if __name__ == "__main__":
    main()
