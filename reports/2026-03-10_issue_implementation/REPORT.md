# 이슈 구현 결과 레포트
**날짜**: 2026-03-10
**브랜치**: `feature/agentic-parsing-and-glossary`

---

## 요약

이번 세션에서 GitHub 이슈 목록을 검토하고, 구현 가능한 2개 이슈를 완료했습니다.

| 이슈 | 제목 | 상태 |
|------|------|------|
| #10 | [Infra] 전역 용어 사전 (Global Terminology Bank) 구축 | ✅ 구현 완료 |
| #13 | [Infra] Feedback Loop - 사용자 피드백 기반 Self-evolving 파이프라인 | ✅ 구현 완료 |

---

## Issue #10 — 전역 용어 사전 (Global Terminology Bank)

### 구현 목표
모든 에이전트가 공유하는 Single Source of Truth 용어 사전 구축 및 번역 파이프라인 통합.

### 변경 파일
- `src/pcm/data/term_bank.json` — 신규 생성 (seed 데이터 207개)
- `src/pcm/core/knowledge_manager.py` — 전체 재구현

### 구현 세부사항

#### 1. term_bank.json — 207개 시드 데이터

| 도메인 | 용어 수 | 주요 용어 예시 |
|--------|--------|----------------|
| algebra | 48 | field→체(體), ring→환(環), group→군(群), kernel→핵(核) |
| analysis | 43 | derivative→도함수, Banach space→바나흐 공간, measure→측도 |
| topology | 39 | manifold→다양체, compact→컴팩트, homotopy→호모토피 |
| category_theory | 38 | functor→함자, natural transformation→자연변환, adjunction→수반 |
| number_theory | 20 | prime→소수, zeta function→제타 함수, elliptic curve→타원 곡선 |
| geometry | 17 | curvature→곡률, geodesic→측지선, Riemannian metric→리만 계량 |

각 항목 스키마:
```json
{
  "field": {
    "translations": {
      "algebra": "체(體)",
      "physics": "장(場)",
      "general": "분야"
    },
    "definition": "A set with addition and multiplication satisfying field axioms",
    "first_seen": "section_1.1",
    "usage_count": 0,
    "confirmed_by": "seed"
  }
}
```

#### 2. KnowledgeManager — 전체 재구현

```python
# 핵심 API
km = KnowledgeManager()

# 도메인 기반 조회 (general 폴백 지원)
km.lookup("field", domain="algebra")   # → "체(體)"
km.lookup("field", domain="physics")   # → "장(場)"

# 용어 등록 (usage_count 자동 추적)
km.register("limit", "극한", domain="analysis", section_id="3.2")

# 번역 프롬프트 주입용 텍스트 생성
km.inject_to_prompt("algebra", top_k=20)
# → "## Terminology Bank (algebra) - top 20 terms\n  - field → 체(體)\n  ..."

# 충돌 감지
km.detect_conflicts()
# → [{"term": "field", "translations": {"algebra": "체(體)", "physics": "장(場)", "general": "분야"}}]

# 전체 통계
km.get_stats()
# → {"total_terms": 207, "domain_breakdown": {...}, "conflict_count": 2}
```

#### 3. 충돌 감지 결과
현재 감지된 충돌 2건:
- `field`: algebra→체(體), physics→장(場), general→분야 (의도된 다의어)
- `limit`: analysis→극한, category_theory→극한 (동일 번역, 도메인만 다름)

#### 4. 수용 기준 달성 현황
- [x] `KnowledgeManager` 클래스 구현 (thread-safe)
- [x] 전역 용어 사전 JSON 스키마 정의 및 seed 데이터 207개 구축 (목표: 200개 이상)
- [x] `inject_to_prompt()` — 번역 파이프라인 주입 로직 구현
- [x] `register()` — 신규 용어 자동 등록 로직
- [x] 충돌 감지 (`detect_conflicts()`) 구현
- [ ] 벤치마크: 100페이지 용어 일관성 비율 측정 (파이프라인 완성 후 측정 예정)

---

## Issue #13 — Feedback Loop (Self-evolving Pipeline)

### 구현 목표
사용자/전문가 피드백을 수집하여 번역 프롬프트에 자동 환류하는 Self-evolving 파이프라인.

### 변경 파일
- `src/pcm/core/feedback_loop.py` — 신규 생성
- `src/pcm/feedback_cli.py` — CLI 도구 신규 생성
- `src/pcm/data/feedback/corrections.json` — 자동 생성 (런타임)

### 구현 세부사항

#### 1. 핵심 클래스

**`FeedbackEntry`** (데이터클래스):
```python
@dataclass
class FeedbackEntry:
    id: str                 # "fb_0001"
    section_id: str         # "2.3"
    correction_type: str    # "term" | "style" | "logic" | "analogy" | "structure"
    original: str           # 수정 전 번역
    corrected: str          # 수정 후 번역
    notes: str              # 수정 이유
    timestamp: str          # ISO 8601
    impact_score: float     # 0.0 ~ 1.0
```

**`ImpactScorer`** — 중요도 점수 계산:
| 유형 | 기본 점수 | 이유 |
|------|-----------|------|
| logic | 1.0 | 논리 오류는 치명적 |
| term | 0.8 | 용어 오류는 반복 적용 가능 |
| structure | 0.7 | 구조 문제는 광범위하게 영향 |
| analogy | 0.6 | 비유 오류는 오해 유발 |
| style | 0.3 | 스타일은 주관적 |

**`FeedbackInjector`** — 번역 프롬프트 주입:
- 동일 섹션 피드백 우선 → 섹션 접두사 매칭 → 전체 피드백 순으로 선택
- impact_score 내림차순 정렬
- Few-shot 형태로 마크다운 블록 생성

#### 2. CLI 사용법

```bash
# 피드백 추가
python src/pcm/feedback_cli.py \
  --add \
  --section 2.3 \
  --type term \
  --original "장" \
  --corrected "체" \
  --notes "대수학 문맥에서 field는 체(體)"

# 대시보드 확인
python src/pcm/feedback_cli.py --dashboard

# 전체 목록
python src/pcm/feedback_cli.py --list

# 섹션별 주입 프리뷰
python src/pcm/feedback_cli.py --inject --section 2.3 --top-k 5
```

#### 3. 실행 결과

**피드백 추가**:
```
Saved feedback [fb_0001]
  Section  : 2.3
  Type     : term
  Original : 장
  Corrected: 체
  Impact   : 1.000
```

**대시보드**:
```
==================================================
  PCM Feedback Dashboard
==================================================
  Total corrections : 2

  By type:
    term            1  #
    style           1  #

  Most frequent corrections (top 10):
     1. [1x]  장 → 체
     2. [1x]  이것은 자명하다 → 이는 명백하다
==================================================
```

**번역 프롬프트 주입 프리뷰**:
```
## Feedback Corrections (section 2.3) - top 2 examples

### Correction example (term, section 2.3)
BEFORE: 장
AFTER:  체
NOTE:   대수학 문맥에서 field는 체(體)
```

#### 4. 수용 기준 달성 현황
- [x] `FeedbackEntry` 데이터클래스 및 JSON 저장소 구현
- [x] `FeedbackProcessor.to_few_shot_example()` 구현
- [x] Impact Score 계산 알고리즘 구현
- [x] 파이프라인 재실행 시 피드백 자동 주입 구현 (`FeedbackInjector`)
- [x] CLI 대시보드 구현 (`--dashboard`, `--add`, `--list`, `--inject`)
- [ ] 전역 용어 사전 자동 업데이트 연동 (KnowledgeManager 연동 후속 작업)
- [ ] 벤치마크: 피드백 50건 누적 후 Critic 평균 점수 변화 (데이터 누적 후 측정 예정)

---

## 미완료 이슈 현황

| 이슈 | 제목 | 미완료 이유 |
|------|------|-------------|
| #4 | TCR 사고형 루프 | 기본 구현 존재. KnowledgeManager 통합 및 로깅 강화 후속 작업 필요 |
| #11 | Layout-aware Parser | `marker-pdf` 라이브러리 설치 및 GPU 환경 구성 필요 |
| #14 | Paper Synthesizer | 복합 에이전트 시스템, 다수 의존성 선행 작업 필요 |
| #18 | 통합 SOP 5단계 | 메타 이슈, 개별 구성요소 완성 후 통합 |
| #6, #7, #8, #9, #12 | Editor/Agent 시리즈 | 파이프라인 기반 구성 완성 후 순차 구현 |

---

## 아키텍처 현황

```
src/pcm/
├── core/
│   ├── knowledge_manager.py   ✅ (완전 재구현, 207개 용어)
│   ├── feedback_loop.py       ✅ (신규 구현)
│   ├── tcr_loop.py            🔧 (기본 구현, 통합 강화 필요)
│   ├── critic_agent.py        🔧 (기본 구현)
│   ├── wsd_agent.py           ✅ (기존 구현)
│   └── ...
├── data/
│   ├── term_bank.json         ✅ (207개 seed)
│   └── feedback/
│       └── corrections.json   ✅ (런타임 생성)
└── feedback_cli.py            ✅ (신규 CLI)
```

---

## 다음 단계 권장 작업

1. **Issue #4 (TCR Loop) 통합 강화**
   - `TCRLoop`에서 `KnowledgeManager.inject_to_prompt()` 호출하여 용어 가이드 주입
   - `FeedbackInjector`를 Translator 프롬프트에 연결

2. **Issue #11 (Layout Parser)**
   - `marker-pdf` 설치 후 블록 유형 분류기 구현
   - Theorem/Proof/Definition 자동 감지

3. **용어 사전 피드백 연동**
   - `FeedbackProcessor`에서 term 유형 수정 시 `KnowledgeManager.register()` 자동 호출
