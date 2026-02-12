import json
import os
import re

class FeynmanLatexGen:
    def __init__(self, template_path=None):
        self.preamble = self._get_default_preamble()
        
    def _get_default_preamble(self):
        return r"""\documentclass[11pt, a4paper, openany]{book}

% ─── 여백 ───
\usepackage[
  top=28mm,
  bottom=25mm,
  inner=25mm,
  outer=30mm,
  marginparwidth=0mm,
  headheight=14pt,
  headsep=14pt
]{geometry}

% ─── 한글 ───
\usepackage{kotex}
\usepackage{fontspec}

% ─── 폰트 ───
\setmainfont{Noto Serif CJK KR}[
  UprightFont={Noto Serif CJK KR},
  BoldFont={Noto Serif CJK KR Bold},
  Ligatures=TeX,
]
\setsansfont{Noto Sans CJK KR}[
  UprightFont={Noto Sans CJK KR},
  BoldFont={Noto Sans CJK KR Bold},
  Ligatures=TeX,
]
\setmonofont{Noto Sans Mono CJK KR}[Scale=0.85]

% ─── 수식 ───
\usepackage{amsmath, amssymb, amsthm}

% ─── 그래픽 ───
\usepackage{graphicx}
\usepackage{tikz}
\usetikzlibrary{arrows.meta, positioning, shapes, calc, decorations.pathreplacing, decorations.markings, patterns, shadows, backgrounds}

% ─── 색상 팔레트 ───
\usepackage{xcolor}
\definecolor{feynred}{HTML}{C0392B}
\definecolor{feynblue}{HTML}{2471A3}
\definecolor{feyndark}{HTML}{1B2631}
\definecolor{feynnote}{HTML}{F0E6D3}
\definecolor{feynlight}{HTML}{EBF5FB}
\definecolor{feyngreen}{HTML}{1E8449}
\definecolor{feyngray}{HTML}{5D6D7E}
\definecolor{feynwarm}{HTML}{FDF2E9}
\definecolor{feyndeep}{HTML}{154360}

% ─── 줄바꿈 ───
\XeTeXlinebreaklocale "ko"
\XeTeXlinebreakskip 0pt plus 3pt
\emergencystretch 5em
\tolerance=2000
\hyphenpenalty=50
\setlength{\hfuzz}{2pt}

% ─── 행간 ───
\linespread{1.65}
\setlength{\parindent}{1.2em}
\setlength{\parskip}{3pt plus 1pt}

% ─── 박스 디자인 (tcolorbox) ───
\usepackage[most]{tcolorbox}

% ◆ 파인만의 말
\newtcolorbox{feynmansays}[1][]{
  enhanced, colback=feynwarm, colframe=feynred!60!black,
  coltitle=white, fonttitle=\sffamily\bfseries\small,
  title={\raisebox{-1pt}{\textbf{!}}~파인만이 강조합니다},
  sharp corners, boxrule=0pt, leftrule=4pt, breakable,
  left=10pt, right=10pt, top=8pt, bottom=8pt,
  shadow={1pt}{-1pt}{0pt}{black!15}, #1
}

% ◆ 역주
\newtcolorbox{translatornote}[1][]{
  enhanced, colback=feynnote, colframe=feyngray!40,
  fonttitle=\sffamily\bfseries\small,
  title={\raisebox{-0.5pt}{\textsf{*}} 역주},
  sharp corners, boxrule=0pt, leftrule=3pt, breakable,
  left=10pt, right=10pt, top=6pt, bottom=6pt,
  fontupper=\small, #1
}

\newtcolorbox{deepresearch}[1][]{
  enhanced, colback=feynlight, colframe=feynblue!70,
  coltitle=white, fonttitle=\sffamily\bfseries\small,
  title={#1}, attach boxed title to top left={yshift=-2mm, xshift=4mm},
  boxed title style={colback=feynblue!80, sharp corners, boxrule=0pt},
  sharp corners, boxrule=0.6pt, breakable,
  left=10pt, right=10pt, top=10pt, bottom=8pt,
  shadow={1.5pt}{-1.5pt}{0pt}{feynblue!15}
}

% ◆ 수식 하이라이트
\newtcolorbox{mathbox}{
  enhanced, colback=feynwarm!50, colframe=feynred!40,
  sharp corners, boxrule=0.5pt,
  left=14pt, right=14pt, top=10pt, bottom=10pt,
  before skip=12pt, after skip=12pt
}

% ◆ 핵심 개념 박스
\newtcolorbox{keyconcept}[1][]{
  enhanced, colback=white, colframe=feyndark, coltitle=white, fonttitle=\sffamily\bfseries,
  title={#1},
  attach boxed title to top center={yshift=-3mm},
  boxed title style={colback=feyndark, sharp corners, boxrule=0pt},
  sharp corners, boxrule=1pt, breakable,
  left=12pt, right=12pt, top=12pt, bottom=10pt
}

\newtcolorbox{diagrambox}[1][]{
  enhanced, colback=white, colframe=feyngray!50,
  fonttitle=\sffamily\small, title={#1},
  attach boxed title to top center={yshift=-2mm},
  boxed title style={colback=feyngray!20, colframe=feyngray!50, boxrule=0.4pt, sharp corners},
  sharp corners, boxrule=0.4pt, breakable,
  left=8pt, right=8pt, top=10pt, bottom=8pt
}

% ◆ 연습 문제 / 생각 해봅시다
\newtcolorbox{exercisebox}{
  enhanced, colback=feyngreen!5, colframe=feyngreen!60,
  fonttitle=\sffamily\bfseries\small,
  title={\textsf{?} 생각해 봅시다},
  sharp corners, boxrule=0pt, leftrule=4pt, breakable,
  left=10pt, right=10pt, top=8pt, bottom=8pt
}

% ─── 헤더/푸터 ───
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE]{{\small\sffamily\color{feyngray} 파인만 물리학 강의 \hfill \thepage}}
\fancyhead[RO]{{\small\sffamily\color{feyngray} \thepage \hfill \rightmark}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\headrule}{\color{feyngray!40}\hrule width\headwidth height\headrulewidth}
\renewcommand{\footrulewidth}{0pt}
\fancypagestyle{plain}{\fancyhf{}\fancyfoot[C]{\small\color{feyngray}\thepage}\renewcommand{\headrulewidth}{0pt}}

% ─── 제목 스타일 ───
\usepackage{titlesec}
\titleformat{\chapter}[display]
  {\normalfont}{\hfill{\fontsize{72}{72}\selectfont\sffamily\color{feynred!20}\thechapter}}{-20pt}
  {\sffamily\bfseries\Huge\color{feyndark}}[\vspace{2pt}{\color{feyngray!40}\titlerule[1pt]}]
\titlespacing*{\chapter}{0pt}{-30pt}{30pt}

\titleformat{\section}[hang]
  {\sffamily\bfseries\LARGE\color{feyndeep}}
  {\thesection}{10pt}{}
\titlespacing*{\section}{0pt}{24pt}{10pt}
\titleformat{\subsection}[hang]{\sffamily\bfseries\large\color{feyndark}}{\thesubsection}{8pt}{}
\titlespacing*{\subsection}{0pt}{16pt}{6pt}

\usepackage{lettrine}
\usepackage{epigraph}
\setlength{\epigraphwidth}{0.75\textwidth}
\renewcommand{\epigraphflush}{center}
\renewcommand{\epigraphrule}{0pt}

\usepackage{hyperref}
\hypersetup{colorlinks=true, linkcolor=feynblue, urlcolor=feynblue!70, pdfborder={0 0 0}, bookmarksnumbered=true, pdftitle={파인만 물리학 강의 — 한국어 번역}, pdfauthor={AI 보조 번역 시스템}}

\setcounter{tocdepth}{2}
\usepackage{enumitem}
\setlist[itemize]{leftmargin=1.5em, itemsep=2pt}
\setlist[enumerate]{leftmargin=1.5em, itemsep=2pt}

\begin{document}
"""

    def _clean_title(self, title):
        if not title: return ""
        # If title is multi-line (common LLM hallucination in titles), take first line
        lines = [l.strip() for l in title.splitlines() if l.strip()]
        if not lines: return ""
        # Strip LLM filler from titles
        import re
        line = lines[0]
        line = re.sub(r'^(물론이죠!?\s*|당연하죠!?\s*|알겠습니다!?\s*)', '', line)
        return line.strip()

    def _escape_latex(self, text):
        if not text: return ""
        # Math-safe LaTeX escaping: protect $...$ and $$...$$ regions
        import re
        parts = re.split(r'(\$\$.*?\$\$|\$.*?\$)', text, flags=re.DOTALL)
        result = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # Inside math — don't escape
                result.append(part)
            else:
                # Outside math — escape special chars
                part = part.replace("&", "\\&").replace("%", "\\%").replace("#", "\\#")
                part = re.sub(r'(?<![\\])_', r'\\_', part)
                result.append(part)
        return "".join(result)

    def _generate_titlepage(self):
        return r"""
% ─────────────────────────────────────────
%  표지
% ─────────────────────────────────────────
\begin{titlepage}
\begin{tikzpicture}[remember picture, overlay]
  \fill[feyndark] (current page.south west) rectangle (current page.north east);
  \foreach \x/\y/\r/\o in {3/20/2.5/8, 15/24/1.8/6, 8/5/3/5, 17/8/2/7, 12/15/1.5/4} {
    \draw[feynred!\o 0, line width=0.8pt] (\x, \y) circle (\r);
  }
  \begin{scope}[shift={(11,12)}, scale=1.5]
    \draw[white!40, line width=1.2pt, decorate, decoration={snake, amplitude=3pt, segment length=8pt}]
      (-2,0) -- (0,0);
    \draw[white!40, line width=1.2pt] (0,0) -- (1.5,1.2);
    \draw[white!40, line width=1.2pt] (0,0) -- (1.5,-1.2);
    \filldraw[white!50] (0,0) circle (3pt);
    \draw[white!40, line width=1.2pt, -Stealth] (1.5,1.2) -- (3,2);
    \draw[white!40, line width=1.2pt, decorate, decoration={snake, amplitude=2pt, segment length=6pt}]
      (1.5,-1.2) -- (3,-0.5);
  \end{scope}
  \node[anchor=west] at (2.5, 18) {
    \begin{minipage}{14cm}
      {\fontsize{14}{18}\selectfont\sffamily\color{feynred!80}\bfseries
        THE FEYNMAN LECTURES ON PHYSICS}
    \end{minipage}
  };
  \node[anchor=west] at (2.5, 15.5) {
    \begin{minipage}{14cm}
      {\fontsize{36}{42}\selectfont\sffamily\color{white}\bfseries
        파인만 물리학 강의}\\[8pt]
      {\fontsize{16}{20}\selectfont\sffamily\color{white!70}
        제1권: 역학, 복사, 열}
    \end{minipage}
  };
  \node[anchor=west] at (2.5, 8) {
    \begin{minipage}{14cm}
      {\Large\sffamily\color{white!80} Richard P. Feynman}\\[4pt]
      {\normalsize\sffamily\color{white!50} Robert B. Leighton \quad Matthew Sands}\\[16pt]
      {\small\sffamily\color{feynred!60} 한국어 번역 · AI 보조 번역 시스템}
    \end{minipage}
  };
  \node[anchor=south] at (current page.south) [yshift=15mm] {
    {\small\sffamily\color{white!30} 개인 학습용 · 비배포}
  };
\end{tikzpicture}
\end{titlepage}

\tableofcontents
\clearpage
"""

    def generate(self, data):
        tex = [self.preamble]
        tex.append(self._generate_titlepage())

        # Chapter
        title_ko = self._clean_title(data.get("chapter_title_ko") or data.get("chapter_title"))
        title_en = data.get("chapter_title")
        
        tex.append(f"\\chapter{{{self._escape_latex(title_ko)}}}")
        tex.append(f"\\label{{ch:{data.get('chapter_id', 'unknown')}}}")
        tex.append(f"\\vspace{{-8pt}}{{\\large\\sffamily\\color{{feyngray}} {self._escape_latex(title_en)}}}")
        tex.append("\\vspace{12pt}")
        
        # Check for epigraph (the famous Feynman quote if available)
        epigraph_text = ""
        # Heuristic: the "cataclysm" quote is often the first feynmansays in Ch 1
        for section in data.get("sections", []):
            for item in section.get("content", []):
                if item.get("type") == "paragraph" and "cataclysm" in item.get("text", "").lower():
                    epigraph_text = item.get("text", "")
                    break
            if epigraph_text: break
            
        if epigraph_text:
            tex.append(f"\\epigraph{{\\itshape ``{epigraph_text}''}}{{--- \\textup{{Richard P. Feynman}}}}")
            tex.append("\\vspace{8pt}")

        is_first_para = True
        for section in data.get("sections", []):
            sec_title = self._clean_title(section.get("title_ko") or section.get("title"))
            tex.append(f"\\section{{{self._escape_latex(sec_title)}}}")
            
            for item in section.get("content", []):
                if item["type"] == "paragraph":
                    text = item.get("text_ko") or item.get("text")
                    # Skip the epigraph text if we already used it
                    if epigraph_text and epigraph_text in (item.get("text") or ""):
                        continue
                        
                    box_type = item.get("box_type")
                    
                    if is_first_para and not box_type:
                        # Apply lettrine to the first character
                        # Korean characters in lettrine need care, but let's try the first syllable
                        if text:
                            first = text[0]
                            rest = text[1:]
                            tex.append(f"\\lettrine[lines=2, loversize=0.15, nindent=0.5em]{{\\color{{feynred}}\\textsf{{{first}}}}}{{{rest}}}\n\n")
                            is_first_para = False
                        else:
                            tex.append("\n\n")
                    elif box_type == "feynmansays":
                        tex.append(f"\\begin{{feynmansays}}\n{text}\n\\end{{feynmansays}}")
                    else:
                        tex.append(text + "\n\n")
                        is_first_para = False # Ensure only the absolute first paragraph gets it
                    
                    # Sub items (notes)
                    for sub in item.get("sub_items", []):
                        if sub["type"] == "translatornote":
                            tex.append(f"\\begin{{translatornote}}\n{sub['text']}\n\\end{{translatornote}}")
                        elif sub["type"] == "deepresearch":
                            title = sub.get("title", "심층 해설")
                            tex.append(f"\\begin{{deepresearch}}{{{self._escape_latex(title)}}}\n{sub['text']}\n\\end{{deepresearch}}")
                
                elif item["type"] == "figure":
                    src = item.get("src")
                    # Image path logic - check images subfolder
                    if not src.startswith("images/"):
                        img_path = os.path.join("feynman_json", "images", os.path.basename(src))
                    else:
                        img_path = os.path.join("feynman_json", src)
                        
                    pdf_path = img_path.replace(".svgz", ".pdf").replace(".svg", ".pdf")
                    
                    caption = self._clean_title(item.get("caption_ko") or item.get("caption"))
                    tex.append("\\begin{center}")
                    tex.append(f"\\begin{{diagrambox}}{{{caption}}}")
                    
                    if os.path.exists(pdf_path):
                        tex.append(f"\\includegraphics[width=0.8\\textwidth]{{{pdf_path}}}")
                    elif os.path.exists(img_path) and not img_path.endswith((".pdf", ".jpg", ".png")):
                         tex.append(f"\\fbox{{Missing vector conversion: {self._escape_latex(os.path.basename(src))}}}")
                    elif os.path.exists(img_path):
                        tex.append(f"\\includegraphics[width=0.8\\textwidth]{{{img_path}}}")
                    else:
                        tex.append(f"\\fbox{{Missing Figure: {self._escape_latex(os.path.basename(src))}}}")
                        
                    tex.append("\\end{diagrambox}")
                    tex.append("\\end{center}")
                
                elif item["type"] == "equation":
                    tex.append(f"\\begin{{mathbox}}\n{item['latex']}\n\\end{{mathbox}}")

        tex.append("\\end{document}")
        return "\n".join(tex)

    def save_tex(self, data, output_path):
        content = self.generate(data)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Saved LaTeX to {output_path}")

if __name__ == "__main__":
    gen = FeynmanLatexGen()
    json_path = "feynman_translated/I_01_enriched.json"
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        gen.save_tex(data, "feynman_translated/I_01.tex")
