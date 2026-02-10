# PDF 레이아웃 디자인 명세서
## The Princeton Companion to Mathematics - 한국어 번역본

> 흑백 프린터 전용 | 전문 서적 품질 | XeLaTeX 기반

---

## 1. 원서 분석 결과

| 항목 | 원서 (PCM) |
|------|-----------|
| 판형 | US Letter (8.5 x 11 in) |
| 레이아웃 | **2단 조판** |
| 단 너비 | 215pt (2.99in) x 2 |
| 단 간격 | 19pt (0.26in) |
| 여백 | L=0.80in, R=1.46in, T=1.79in, B=0.90in |
| 본문 폰트 | Lucida Bright @ 8.1pt |
| 수식 폰트 | Lucida NewMath @ 8.1pt |
| 총 페이지 | 1,057쪽 |

### 원서 타이포그래피 계층

```
Part 제목     : LucidaBright-Demi  28.4pt  (예: "Part I")
Chapter 제목  : LucidaBright-Demi  15.7pt  (예: "Contents")
Section 번호  : LucidaBright-Demi   9.0pt  (예: "2", "3")
Subsection    : LucidaBright-Demi   8.1pt  (예: "2.2 Equivalence...")
본문          : LucidaBright         8.1pt
이탤릭/강조   : LucidaBright-Italic  8.1pt
각주/첨자     : LucidaBright         6.0pt
Running header: 섹션명 + 페이지 번호
```

---

## 2. 한국어 번역본 디자인 결정

### 2.1 판형: A4 (210 x 297 mm)

이유: 한국 표준 프린터 용지. US Letter 대비 약간 길고 좁음.

### 2.2 레이아웃: **단단 (1단) 조판**

원서는 2단이지만 한국어 번역본은 **1단**으로 변경.

이유:
- 한글은 영문 대비 글자당 폭이 넓어 2단에서 줄 길이가 너무 짧아짐
- 2단 × 한글 = 줄당 15-18자 → 가독성 심각하게 저하
- 1단 = 줄당 35-40자 → 한글 최적 가독성 범위
- 수식이 2단 폭에 들어가지 않는 경우 빈번

### 2.3 여백 설계

```
              ┌─────────────────────────────┐
              │       top = 25mm            │
              │  ┌───────────────────────┐  │
              │  │   Running Header      │  │
              │  │                       │  │
   left 30mm  │  │                       │  │  right 25mm
   (제본쪽)   │  │    Text Area          │  │
              │  │    155mm x 237mm      │  │
              │  │                       │  │
              │  │                       │  │
              │  └───────────────────────┘  │
              │       bottom = 20mm         │
              │       [page number]         │
              └─────────────────────────────┘
```

| 여백 | 치수 | 비고 |
|------|------|------|
| 상단 | 25mm | 러닝 헤더 포함 |
| 하단 | 20mm | 페이지 번호 영역 |
| 안쪽 (제본) | 30mm | 제본 시 접히는 부분 고려 |
| 바깥쪽 | 25mm | |
| 텍스트 영역 | 155mm x 237mm | |

> 제본 여백은 `\geometry`의 `bindingoffset=5mm` 으로 별도 처리

### 2.4 폰트 설계

#### 본문: Noto Serif CJK KR (10.5pt)

| 용도 | 폰트 | 크기 | 행간(leading) |
|------|------|------|---------------|
| 본문 | Noto Serif CJK KR Regular | 10.5pt | 16pt (1.52x) |
| 강조 | Noto Serif CJK KR Bold | 10.5pt | 16pt |
| 수식 내 텍스트 | Latin Modern Math | 10.5pt | - |

왜 10.5pt인가:
- 원서 8.1pt는 Lucida Bright 기준 (x-height가 큰 폰트)
- 한글은 구조가 복잡해 최소 10pt 이상 필요
- 10.5pt는 한국 학술서적의 표준 본문 크기
- 흑백 인쇄 시 10pt 미만은 획이 뭉침

#### 제목 체계: Noto Sans CJK KR

| 계층 | 폰트 | 크기 | 스타일 | 간격 |
|------|------|------|--------|------|
| Part | Noto Sans CJK KR Black | 28pt | 별도 페이지 | 전: 새 페이지, 후: 40pt |
| Chapter | Noto Sans CJK KR Bold | 18pt | 별도 페이지 | 전: 새 페이지, 후: 24pt |
| Section (예: "2") | Noto Sans CJK KR Bold | 14pt | - | 전: 30pt, 후: 12pt |
| Subsection (예: "2.2") | Noto Sans CJK KR Bold | 12pt | - | 전: 20pt, 후: 8pt |
| Subsubsection | Noto Sans CJK KR Medium | 10.5pt | - | 전: 14pt, 후: 6pt |

#### 수식: Latin Modern Math

- `unicode-math` 패키지 사용
- 인라인 수식과 디스플레이 수식 모두 지원
- 한글 본문과 자연스러운 크기 매칭

#### 코드/고정폭: Noto Sans Mono CJK KR

- 수학 표기에서 코드 스니펫이 나올 경우 사용
- 9pt, 행간 13pt

### 2.5 행간 및 단락 설계

```
본문 행간     : 16pt (baselineskip)     ← 본문 10.5pt의 1.52배
단락 간격     : 0pt (parskip)           ← 들여쓰기로 단락 구분
단락 들여쓰기 : 1em (약 10.5pt)         ← 한국 서적 표준
```

왜 parskip=0 + indent 방식인가:
- 원서가 이 방식 사용
- 학술서적 표준
- 수식 전후 간격과 충돌하지 않음
- 프린트 시 종이 절약

### 2.6 수식 레이아웃

```latex
% 인라인 수식: 본문 흐름 유지
군 $G$의 원소 $x$에 대해 $x^n = e$이면...

% 디스플레이 수식: 별도 줄, 번호 있음
\begin{equation}
  \sqrt{2} \text{는 무리수이다}
\end{equation}

% 번호 없는 수식
\[
  p(x) = 0 \quad \text{일 때} \quad x = \frac{3 \pm \sqrt{5}}{2}
\]
```

- 디스플레이 수식 전후: `abovedisplayskip = 12pt`, `belowdisplayskip = 12pt`
- 수식 번호: 오른쪽 정렬, `(섹션.수식번호)` 형식

### 2.7 러닝 헤더/푸터

```
┌─────────────────────────────────────────┐
│ I.4  수학 연구의 일반적 목표         67 │  ← 짝수 페이지
├─────────────────────────────────────────┤
│ 67         2.2 동치, 비동치, 그리고 불변량 │  ← 홀수 페이지
└─────────────────────────────────────────┘
```

| 위치 | 짝수(왼쪽) 페이지 | 홀수(오른쪽) 페이지 |
|------|------------------|-------------------|
| 헤더 왼쪽 | 섹션 번호 + 제목 | 페이지 번호 |
| 헤더 오른쪽 | 페이지 번호 | 서브섹션 번호 + 제목 |
| 푸터 | (없음) | (없음) |

- 헤더 구분선: 0.4pt 실선
- 헤더 폰트: Noto Sans CJK KR Regular 8.5pt
- 헤더와 본문 사이: 12pt

### 2.8 특수 요소 디자인

#### 박스/정의/정리

```
┌─ 정의 1.3.1 ─────────────────────────────┐
│                                           │
│  군(group)이란 집합 G와 이항 연산           │
│  · : G × G → G로 이루어진 순서쌍 (G, ·)을   │
│  말하며, 다음 조건을 만족한다:              │
│  ...                                      │
│                                           │
└───────────────────────────────────────────┘
```

- 테두리: 0.5pt 실선 (흑백 인쇄에 최적)
- 내부 패딩: 8pt
- 제목 라벨: Noto Sans CJK KR Bold 10pt
- 배경: 없음 (흑백 프린터 - 회색 배경은 토너 낭비)

#### 교차 참조

원서의 `[IV.1§14]` 같은 참조:
- 본문 내 `[IV.1§14]` 형태 유지
- 볼드 처리하지 않음 (흑백에서 구분 충분)

#### 각주

- 본문 하단, 구분선(3cm) 아래
- 8pt Noto Serif CJK KR, 행간 11pt
- 번호: 아라비아 숫자, 섹션 단위 리셋

### 2.9 이미지/도표

- 최대 폭: 텍스트 영역 폭 (155mm)
- 해상도: 최소 300dpi (프린트용)
- 캡션: 이미지 아래, Noto Sans CJK KR 9pt
- 캡션 형식: "그림 1.3: 정다면체의 분류"

---

## 3. 페이지 유형별 레이아웃

### 3.1 Part 시작 페이지

```
              (상단 1/3 비움)

              ━━━━━━━━━━━━━━━━━━
                  제 I 부

                   소개
              ━━━━━━━━━━━━━━━━━━

              (하단 2/3 비움)
              (페이지 번호 없음)
```

### 3.2 Section 시작 페이지

```
              I.4  수학 연구의 일반적 목표
              ━━━━━━━━━━━━━━━━━━━━━━━━━━━

              본문 시작...
```

- Section 제목 후 2pt 실선
- 본문은 제목 아래 24pt 간격 후 시작

### 3.3 일반 본문 페이지

```
    ┌─────────────────────────────────────┐
    │ I.4  수학 연구의 일반적 목표     76 │ ← header
    │ ─────────────────────────────────── │ ← 0.4pt rule
    │                                     │
    │   본문 텍스트가 여기에 들어갑니다.   │
    │ 군 $G$의 원소 $x$에 대해 $x^n = e$  │
    │ 이면 $x$는 유한 위수를 가진다고      │
    │ 한다.                               │
    │                                     │
    │   가장 작은 그러한 거듭제곱을 $x$의  │
    │ 위수라 부른다. 예를 들어, 법 7에     │
    │ 대한 0이 아닌 정수들의 곱셈군에서    │
    │ 항등원은 1이고, 원소 4의 위수는      │
    │ 3이다.                              │
    │                                     │
    │   \[                                │
    │     4^1 = 4,\; 4^2 = 16 \equiv 2,  │
    │     \; 4^3 = 64 \equiv 1 \pmod{7}  │
    │   \]                                │
    │                                     │
    └─────────────────────────────────────┘
```

---

## 4. XeLaTeX 구현 구조

### 4.1 파일 구조

```
latex/
├── main.tex              ← 마스터 문서
├── preamble.tex          ← 패키지/폰트/스타일 설정
├── macros.tex            ← 수학 매크로, 번역 용어
├── glossary.tex          ← 수학 용어 사전
├── parts/
│   ├── part1.tex         ← Part I: 소개
│   ├── part2.tex         ← Part II: 현대 수학의 기원
│   └── ...
├── sections/
│   ├── I_1.tex           ← I.1 소개의 소개
│   ├── I_2.tex           ← I.2 ...
│   └── ...
├── images/
│   └── (추출된 이미지)
└── build.sh              ← 빌드 스크립트
```

### 4.2 핵심 LaTeX 설정

```latex
% preamble.tex

\documentclass[10.5pt, a4paper, twoside, openright]{book}

% === 여백 ===
\usepackage[
  top=25mm,
  bottom=20mm,
  inner=30mm,
  outer=25mm,
  bindingoffset=5mm,
  headheight=14pt,
  headsep=12pt
]{geometry}

% === 한글 ===
\usepackage{kotex}           % 한국어 지원 핵심
\usepackage{fontspec}

% === 폰트 ===
\setmainfont{Noto Serif CJK KR}[
  BoldFont={Noto Serif CJK KR Bold},
  UprightFont={Noto Serif CJK KR},
]
\setsansfont{Noto Sans CJK KR}[
  BoldFont={Noto Sans CJK KR Bold},
  UprightFont={Noto Sans CJK KR Regular},
]
\setmonofont{Noto Sans Mono CJK KR}

% === 수식 ===
\usepackage{amsmath, amssymb, amsthm}
\usepackage{unicode-math}
\setmathfont{Latin Modern Math}

% === 행간 ===
\usepackage{setspace}
\setstretch{1.52}            % 본문 행간

% === 단락 ===
\setlength{\parindent}{1em}
\setlength{\parskip}{0pt}

% === 헤더/푸터 ===
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE]{\small\nouppercase{\leftmark} \hfill \thepage}
\fancyhead[RO]{\small\thepage \hfill \nouppercase{\rightmark}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0pt}

% === 제목 스타일 ===
\usepackage{titlesec}

% Part
\titleformat{\part}[display]
  {\centering\sffamily\bfseries\Huge}
  {제 \thepart 부}{20pt}{\Huge}
\titlespacing*{\part}{0pt}{100pt}{40pt}

% Chapter (= Section in PCM)
\titleformat{\chapter}[hang]
  {\sffamily\bfseries\LARGE}
  {\thechapter}{12pt}{}
  [\vspace{2pt}\titlerule]
\titlespacing*{\chapter}{0pt}{30pt}{24pt}

% Section (= Subsection in PCM)
\titleformat{\section}[hang]
  {\sffamily\bfseries\Large}
  {\thesection}{8pt}{}
\titlespacing*{\section}{0pt}{20pt}{8pt}

% Subsection
\titleformat{\subsection}[hang]
  {\sffamily\bfseries\normalsize}
  {\thesubsection}{6pt}{}
\titlespacing*{\subsection}{0pt}{14pt}{6pt}

% === 정리/정의 환경 ===
\usepackage{tcolorbox}
\tcbuselibrary{theorems, breakable}

\newtcbtheorem[number within=chapter]{definition}{정의}{
  colback=white, colframe=black,
  fonttitle=\sffamily\bfseries,
  breakable, sharp corners,
  boxrule=0.5pt
}{def}

\newtcbtheorem[number within=chapter]{theorem}{정리}{
  colback=white, colframe=black,
  fonttitle=\sffamily\bfseries,
  breakable, sharp corners,
  boxrule=0.5pt
}{thm}

% === 교차참조 ===
\usepackage{hyperref}
\hypersetup{
  colorlinks=false,          % 흑백 인쇄: 색상 링크 끔
  pdfborder={0 0 0},
  bookmarksnumbered=true,
}

% === 목차 ===
\usepackage{tocloft}
\renewcommand{\cftpartfont}{\sffamily\bfseries\large}
\renewcommand{\cftchapfont}{\sffamily\bfseries}
\renewcommand{\cftsecfont}{\rmfamily}

% === 색인 ===
\usepackage{makeidx}
\makeindex
```

### 4.3 Python → LaTeX 변환 규칙

JSON 번역 결과를 LaTeX으로 변환할 때 적용할 규칙:

| 원본 요소 | LaTeX 변환 |
|-----------|-----------|
| Part 제목 | `\part{제 I 부: 소개}` |
| Section 번호 (예: "2") | `\chapter{일반화}` |
| Subsection (예: "2.2") | `\section{동치, 비동치, 그리고 불변량}` |
| 본문 단락 | 빈 줄로 구분 |
| 인라인 수식 `$...$` | 그대로 유지 |
| 디스플레이 수식 | `\[...\]` 또는 `equation` 환경 |
| 교차참조 `[IV.1§14]` | `\hyperref[sec:IV.1.14]{[IV.1\S14]}` |
| 이미지 | `\includegraphics` + `figure` 환경 |
| 볼드 용어 | `\textbf{...}` 또는 `\term{...}` |
| 이탤릭 | `\textit{...}` (영문만, 한글에는 고딕체 사용) |

---

## 5. 인쇄 최적화 (흑백 전용)

### 5.1 잉크/토너 절약
- 배경색 일체 없음 (모든 박스 `colback=white`)
- 회색 음영 사용하지 않음
- 실선 두께: 0.4pt (헤더), 0.5pt (박스) — 인쇄 시 선명

### 5.2 양면 인쇄 대응
- `twoside` 옵션으로 좌우 여백 교차
- 안쪽 여백(제본) 30mm + binding 5mm = 35mm
- Part/Chapter는 `openright` (홀수 페이지 시작)

### 5.3 흑백 구분 요소
색상 대신 사용할 시각적 구분:
- **볼드**: 정의되는 용어, 제목
- **이탤릭**: 영문 고유명사, 강조
- **실선 박스**: 정의, 정리
- **들여쓰기**: 인용, 보조 설명
- **글꼴 변경**: 산세리프(제목) vs 세리프(본문)

### 5.4 예상 출력
- A4 단면 기준 약 650-700쪽 (원서 1,057쪽의 약 65%)
- 한글은 영문보다 정보 밀도가 높아 페이지 수 감소
- 1단 조판이지만 행간/여백 최적화로 페이지 효율 유지

---

## 6. 빌드 파이프라인

```
[JSON sections] → json_to_latex.py → [.tex files] → XeLaTeX → PDF
                     ↑
              glossary.json (수학 용어 사전)
```

### 빌드 명령

```bash
# 1회 빌드
xelatex -interaction=nonstopmode main.tex

# 목차/색인 포함 전체 빌드
xelatex main.tex && makeindex main.idx && xelatex main.tex && xelatex main.tex
```

---

## 7. 시각적 비교 요약

| 항목 | 원서 (PCM) | 번역본 (본 디자인) |
|------|-----------|------------------|
| 판형 | US Letter | **A4** |
| 조판 | 2단 | **1단** |
| 본문 폰트 | Lucida Bright 8.1pt | **Noto Serif CJK KR 10.5pt** |
| 제목 폰트 | Lucida Bright Demi | **Noto Sans CJK KR Bold** |
| 수식 | Lucida NewMath | **Latin Modern Math** |
| 행간 | ~1.2x | **1.52x** (한글 최적) |
| 여백 | 비대칭 | **양면 제본 대칭** |
| 색상 | 흑백 | **흑백** |
| 헤더 | 섹션 + 페이지 | **섹션 + 페이지 (동일)** |
| 특수 요소 | 인라인 처리 | **실선 박스** |
