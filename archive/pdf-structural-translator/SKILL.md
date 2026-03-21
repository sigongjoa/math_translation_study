---
name: pdf-structural-translator
description: PDF 문서의 폰트/스타일 패턴(Font, Size, End-markers)을 분석하여 수학적 구조(Definition, Example, Remark)를 추출하고, 이를 기반으로 구조화된 한국어 번역을 수행합니다.
---

# PDF Structural Translator Skill

이 스킬은 수학/과학 전문 서적의 PDF를 번역할 때, 단순한 텍스트 추출이 아닌 **문서의 논리적 아키텍처(Architecture)**를 보존하며 번역하기 위한 가이드입니다.

## 🚀 Core Workflow

### 1. Pattern Discovery (패턴 탐색)
PDF의 샘플 페이지(주로 Chapter 1)를 분석하여 다음 요소를 식별합니다.
- **Structural Keywords**: Definition, Example, Exercise, Remark, Proposition, Theorem 등.
- **Font Signatures**: 키워드에 사용된 특정 폰트(예: `TeXGyrePagellaX-Bold`, `*-Italic`).
- **End Markers**: 블록의 종료를 알리는 특수 기호(예: `♦`, `■`)와 해당 폰트(`txsya`).

### 2. Block-Based Parsing (블록 단위 파싱)
추출된 패턴을 기반으로 전체 문서를 다음 형태의 JSON 블록 리스트로 변환합니다.
- `type`: `definition`, `exercise`, `text` 등
- `id`: `1.30` 등의 번호
- `content_en`: 원문 텍스트
- `is_structural`: True/False

### 3. Context-Aware Translation (문맥 인지 번역)
각 블록의 `type`에 맞는 프롬프트를 사용하여 번역을 수행합니다.
- **Definition**: 엄밀한 용어 선택, 반사성/전이성 등의 수학 용어 일관성 유지.
- **Exercise**: '~하세요', '~구하시오' 등 활동 중심의 명령조 어미 사용.
- **Remark/Example**: 친절하고 명확한 설명조 어미 사용.

### 4. Layout Assembly (레이아웃 조립)
번역된 블록의 `type` 정보를 바탕으로 LaTeX의 `tcolorbox` 환경을 자동 매핑합니다.
- `definition` -> `\begin{definitionbox}`
- `exercise` -> `\begin{exercisebox}`
- `remark` -> `\begin{remarkbox}` (신규 디자인 권장)

## 🛠️ Usage with Core Module
이 스킬은 `src/pcm/core/structure_analyzer.py` 모듈과 함께 사용됩니다.

```python
from pcm.core.structure_analyzer import PDFStructureAnalyzer

# 1. 구조 분석
analyzer = PDFStructureAnalyzer("book.pdf")
blocks = analyzer.extract_blocks(21, 50)

# 2. 블록별 번역 및 LaTeX 생성
# (이후 워크플로우는 pipeline.py에서 처리)
```

## 📋 디자인 가이드 (Remark 추가)
- **Remark(비고)**: 독자의 주의를 환기시키는 보충 정보이므로, 차분한 **보라색(ctnote)** 또는 **회색(ctgray)** 테두리의 얇은 박스로 디자인합니다.
