---
name: glossary-architect
description: 수학/기술 서적의 챕터 원문을 분석하여 핵심 용어를 추출하고, 딥리서치(검색)를 통해 가장 엄밀한 학술 한국어 용어 사전(JSON)을 자동 구축합니다.
---

# Glossary Architect Skill

이 스킬은 번역의 '수학적 엄밀성'을 보장하기 위해, 도메인별 표준 용어를 사전에 확정하는 에이전트 워크플로우를 제공합니다.

## 🚀 Core Workflow

### 1. Concept Discovery
- 챕터 원문을 스캔하여 기술 용어 후보를 추출합니다.
- `src/pcm/core/glossary_architect.py`의 추출 로직을 활용합니다.

### 2. Deep Research (교차 검증)
추출된 각 용어에 대해 다음 순서로 검색 및 검증을 수행합니다:
1.  **도메인 판별**: 이 텍스트가 범주론(Category Theory)인지, 집합론(Set Theory)인지 파악합니다.
2.  **KMS/위키백과 검색**: 대한수학회 용어집 및 한국어 위키백과를 검색하여 표준 번역어를 찾습니다.
3.  **오역 방지**: 일반적인 단어 뜻(예: Preorder -> 사전식 순서)이 수학적 문맥에 맞지 않는 경우, 전문 커뮤니티의 관례를 조사합니다.

### 3. Artifact Creation
- 검증된 용어 쌍을 `src/pcm/data/glossaries/seven_sketches_ch[N].json` 형태로 저장합니다.

## 📋 검증 가이드 (예: Preorder)
- **용어**: Preorder
- **일반 뜻**: 사전식 순서 (Lexicographical order와 혼동 주의)
- **범주론 뜻**: **전순서** 또는 **준순서**
- **결정**: 문맥이 'Reflexivity', 'Transitivity'를 다루고 있다면 무조건 **전순서**로 확정.
