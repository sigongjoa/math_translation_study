# Workspace

번역 작업 디렉토리입니다. 책 1권 = 이 디렉토리 1개.

## 파일 구조

```
workspace/
├── sections.json       ← /parse-pdf 출력
├── glossary.json       ← /build-glossary 출력 (직접 편집 가능)
├── translated/         ← /translate-section 출력
│   ├── p001_s001.json
│   ├── p001_s002.json
│   └── ...
├── review_report.md    ← /review-batch 출력
└── output.tex          ← /assemble-output 출력
```

## 워크플로우

```bash
# 1. PDF 파싱
/parse-pdf book.pdf --pages 1-50

# 2. 용어집 구축 (glossary.json 직접 수정 가능)
/build-glossary --domain mathematics

# 3. 섹션별 번역
/translate-section --page 1
/translate-section --pages 1-10
/translate-section --all

# 4. 품질 검토 (용어 불일치, 수식 누락 등)
/review-batch

# 5. 조립
/assemble-output --title "번역서 제목"
```

## 여러 책 작업 시

이 디렉토리를 복사해서 사용:
```bash
cp -r workspace workspace_princeton_ch1
cp -r workspace workspace_arxiv_2401_12345
```
