#!/usr/bin/env python3
"""
Pipeline Validation Suite
--unit    : Ollama 없이 구조/계약/에러격리/Resume 검증 (~10초)
--ollama  : 실제 번역 + TCR 검증 (~2분, Ollama 필요)
기본값: --unit
"""

import sys, json, sqlite3, time, os, io, contextlib, requests, argparse
sys.path.insert(0, "/mnt/d/progress/the princeton companion to mathematics")

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
INFO = "\033[94m[INFO]\033[0m"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  {status} {name}" + (f"  ({detail})" if detail else ""))
    results.append((name, condition))
    return condition

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

parser = argparse.ArgumentParser()
parser.add_argument("--ollama", action="store_true", help="Include live Ollama tests")
args = parser.parse_args()

DB_PATH = "pipeline_test.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)


# ──────────────────────────────────────────────
# 0. 환경
# ──────────────────────────────────────────────
section("0. 환경 확인")

try:
    r = requests.get("http://localhost:11434/api/tags", timeout=3)
    models = [m["name"] for m in r.json().get("models", [])]
    ollama_ok = "qwen2.5:7b" in models
    check("Ollama qwen2.5:7b", ollama_ok, f"models={models}")
except Exception as e:
    ollama_ok = False
    check("Ollama qwen2.5:7b", False, str(e))

if args.ollama and not ollama_ok:
    print(f"\n  {FAIL} --ollama 지정됐으나 Ollama 미가동. 종료.")
    sys.exit(1)


# ──────────────────────────────────────────────
# 1. DB 계층 구조
# ──────────────────────────────────────────────
section("1. DB 계층 구조 (Job→Stage→Section→Iteration→Log)")

from src.pcm.pipeline.db import PipelineDB
db = PipelineDB(DB_PATH)

job_id = db.create_job("test://validation.pdf", 1, 5)
job = db.get_job(job_id)
check("Job 생성", job is not None, f"id={job_id}")
check("Job 기본 상태 pending", job["status"] == "pending")

st = db.get_or_create_stage(job_id, 1, "Domain Orientation")
check("Stage 생성 + job_id 연결", st is not None and st["job_id"] == job_id)

# get_or_create 멱등성 — 두 번 호출해도 같은 id
st2 = db.get_or_create_stage(job_id, 1, "Domain Orientation")
check("Stage get_or_create 멱등성", st["id"] == st2["id"])

sec_id = db.create_section(job_id, st["id"], "1.1",
                           "A group is a set $G$ with a binary operation.")
check("Section 생성", sec_id is not None)

iter1 = db.add_iteration(sec_id, job_id, 1, "Translator",
    "군은 이항 연산을 갖는 집합이다.", 65.0, "용어 개선 필요")
iter2 = db.add_iteration(sec_id, job_id, 2, "Refiner",
    "군(群)은 이항 연산이 정의된 집합 $G$이다.", 88.0, "PASS")
check("Iteration 2회 저장", iter1 and iter2)

# 이터레이션 점수 궤적 확인
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
iters = conn.execute("SELECT iteration_num, score FROM iterations WHERE section_id=? ORDER BY iteration_num", (sec_id,)).fetchall()
scores = [i["score"] for i in iters]
check("Iteration 점수 궤적 저장 (65→88)", scores == [65.0, 88.0], f"scores={scores}")

# 로그 3종
db.log(job_id, "WSDAgent", "INFO", "algebra 도메인 분류", stage_num=1, section_id=sec_id)
db.log(job_id, "TCRLoop", "WARNING", "score 65 < threshold 80", stage_num=3, section_id=sec_id)
db.log(job_id, "Ollama", "ERROR", "timeout", stage_num=2,
       details={"elapsed": 60.1})
all_logs = db.get_logs(job_id)
err_logs = db.get_logs(job_id, level="ERROR")
check("전체 로그 3건 저장", len(all_logs) == 3, f"count={len(all_logs)}")
check("ERROR 필터링", len(err_logs) == 1)
check("ERROR details JSON 저장", err_logs[0].get("details") is not None)

summary = db.get_job_summary(job_id)
check("Job Summary 반환", summary is not None)
check("Summary.stages 포함", "stages" in summary)

db.update_job_status(job_id, "completed")
check("Job 상태 업데이트", db.get_job(job_id)["status"] == "completed")


# ──────────────────────────────────────────────
# 2. Stage 간 데이터 계약
# ──────────────────────────────────────────────
section("2. Stage 간 데이터 계약 검증")

from src.pcm.pipeline.stages import Stage1_Orientation, Stage2_Drafting, Stage4_Validation
from src.pcm.pipeline.logger import PipelineLogger

test_sections = [
    {"section_id": "c1.1", "text": "A field is a commutative ring where every nonzero element has an inverse."},
    {"section_id": "c1.2", "text": "A topological space $(X, \\tau)$ consists of a set $X$ and a topology $\\tau$."},
]
cj_id = db.create_job("test://contract.pdf", 1, 2)
cj = db.get_job(cj_id)

# Stage1 계약 확인
st1 = db.get_or_create_stage(cj_id, 1, "Domain Orientation")
r1 = Stage1_Orientation().run(cj, st1, test_sections, db, PipelineLogger(db, cj_id, 1))
check("Stage1 출력: sections 키", "sections" in r1)
check("Stage1: 각 섹션에 domain 필드", all("domain" in s for s in r1["sections"]),
      str([s.get("domain") for s in r1["sections"]]))
check("Stage1: terminology_guide 필드", all("terminology_guide" in s for s in r1["sections"]))
check("Stage1: section_id 보존", {s["section_id"] for s in r1["sections"]} == {"c1.1","c1.2"})
check("Stage1: DB section 레코드 생성",
      len(db.get_sections_for_stage(st1["id"])) == 2)

# Stage2 계약 (Ollama 없으면 fallback=원문으로 동작)
st2 = db.get_or_create_stage(cj_id, 2, "Initial Draft")
r2 = Stage2_Drafting().run(cj, st2, r1["sections"], db, PipelineLogger(db, cj_id, 2))
check("Stage2 출력: sections 키", "sections" in r2)
check("Stage2: draft_ko 필드 존재", all("draft_ko" in s for s in r2["sections"]),
      str(list(r2["sections"][0].keys())))
check("Stage2: draft_ko 비어있지 않음", all(s.get("draft_ko") for s in r2["sections"]))

# Stage4 계약
st4 = db.get_or_create_stage(cj_id, 4, "Consistency Validation")
# Stage4는 final_ko 필요 — Stage2 draft를 final_ko로 채워줌
for s in r2["sections"]:
    s["final_ko"] = s.get("draft_ko", s["text"])
    s["final_score"] = 75.0
r4 = Stage4_Validation().run(cj, st4, r2["sections"], db, PipelineLogger(db, cj_id, 4))
check("Stage4 출력: sections 키", "sections" in r4)
check("Stage4: summary.total_inconsistencies 포함",
      "total_inconsistencies" in r4.get("summary", {}),
      str(r4.get("summary")))


# ──────────────────────────────────────────────
# 3. 에러 격리 검증
# ──────────────────────────────────────────────
section("3. 에러 격리 — 한 섹션 실패가 나머지에 영향 없음")

broken_sections = [
    {"section_id": "e1.1", "text": "Valid section about groups and rings."},
    {"section_id": "e1.2", "text": None},   # None → 실패 유발
    {"section_id": "e1.3", "text": "Valid section about topology and manifolds."},
]
ej_id = db.create_job("test://errors.pdf", 1, 3)
ej = db.get_job(ej_id)
est = db.get_or_create_stage(ej_id, 1, "Domain Orientation")
re = Stage1_Orientation().run(ej, est, broken_sections, db, PipelineLogger(db, ej_id, 1))

valid = [s for s in re.get("sections", []) if s.get("domain")]
errs  = db.get_logs(ej_id, level="ERROR")
check("Stage가 중단되지 않음 (sections 반환)", "sections" in re)
check("정상 섹션 2개 처리 완료", len(valid) >= 2, f"{len(valid)}/3 성공")
check("실패 섹션 ERROR 로그 기록", len(errs) >= 1, f"{len(errs)}건")


# ──────────────────────────────────────────────
# 4. Resume 기능 검증
# ──────────────────────────────────────────────
section("4. Resume — 완료된 단계 SKIP")

from src.pcm.pipeline.master import MasterPipeline
pipeline = MasterPipeline(db_path=DB_PATH)

resume_sections = [{"section_id": "r1.1", "text": "A ring has addition and multiplication."}]

rj_id = pipeline.run("test://resume.pdf", 1, 1, sections_override=resume_sections)
check("1차 실행 완료", db.get_job(rj_id)["status"] == "completed")

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    pipeline.run("test://resume.pdf", 1, 1, job_id=rj_id, sections_override=resume_sections)
skip_count = buf.getvalue().count("[SKIP]")
check("Resume 시 5단계 모두 SKIP", skip_count == 5, f"SKIP={skip_count}")

# 미완료 job resume — 2단계만 완료 후 재개
partial_job_id = db.create_job("test://partial.pdf", 1, 1)
partial_st1 = db.get_or_create_stage(partial_job_id, 1, "Domain Orientation")
db.update_stage_status(partial_st1["id"], "completed")  # 1단계만 완료로 표시

buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    pipeline.run("test://partial.pdf", 1, 1, job_id=partial_job_id, sections_override=resume_sections)
output2 = buf2.getvalue()
skip1 = "[SKIP] Stage 1" in output2
run2  = "[RUN] Stage 2" in output2
check("부분 Resume: Stage1 SKIP", skip1)
check("부분 Resume: Stage2부터 실행", run2)


# ──────────────────────────────────────────────
# 5. 용어 사전 주입
# ──────────────────────────────────────────────
section("5. 용어 사전 주입 (KnowledgeManager)")

from src.pcm.core.knowledge_manager import KnowledgeManager
km = KnowledgeManager()

p = km.inject_to_prompt("algebra", top_k=10)
check("inject_to_prompt 비어있지 않음", len(p) > 50, f"{len(p)}자")
p_full = km.inject_to_prompt("algebra", top_k=50)
check("algebra 용어 포함 (체/field)", "체" in p_full or "field" in p_full.lower())
check("algebra 용어 포함 (환/ring)", "환" in p or "ring" in p.lower())

stats = km.get_stats()
check("용어 200개 이상", stats["total_terms"] >= 200, f"{stats['total_terms']}개")
check("충돌 감지 결과 포함", "conflict_count" in stats, f"{stats.get('conflict_count')}건")

conflicts = km.detect_conflicts()
check("충돌 detect_conflicts() 동작", isinstance(conflicts, list))


# ──────────────────────────────────────────────
# 6. Ollama 실제 번역 (--ollama 플래그 시)
# ──────────────────────────────────────────────
if args.ollama:
    section("6. 실제 번역 검증 (Ollama qwen2.5:7b)")

    terminology = km.inject_to_prompt("algebra", top_k=5)
    try:
        t0 = time.time()
        resp = requests.post("http://localhost:11434/api/generate", json={
            "model": "qwen2.5:7b",
            "prompt": (
                f"다음 수학 텍스트를 한국어로 번역하세요.\n"
                f"용어 사전:\n{terminology}\n\n"
                f"Text: A group $G$ is a set with a binary operation satisfying "
                f"associativity, identity, and inverses.\n\n번역:"
            ),
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 150}
        }, timeout=60)
        elapsed = time.time() - t0
        tr = resp.json().get("response", "").strip()
        has_ko = any('\uAC00' <= c <= '\uD7A3' for c in tr)
        has_G  = "$G$" in tr or "G" in tr
        check("한국어 번역 생성", has_ko, tr[:60])
        check("수식 $G$ 보존", has_G)
        check("응답 시간 < 30초", elapsed < 30, f"{elapsed:.1f}s")
        print(f"  {INFO} 결과: {tr[:100]}")
    except Exception as e:
        check("Ollama 번역 호출", False, str(e))

    # TCR 1회 루프 검증
    section("6b. TCR Loop 단축 검증 (1 iteration)")
    from src.pcm.core.tcr_loop import TCRLoop
    tcr = TCRLoop(model="qwen2.5:7b", threshold=100, max_iterations=1)  # threshold=100 → 항상 1회
    glossary = {"group": "군(群)", "ring": "환(環)", "field": "체(體)"}
    prompt = "당신은 수학 전문 번역가입니다."
    try:
        ko, trace = tcr.run("A field has addition and multiplication.", glossary, prompt)
        has_iter = len(trace["iterations"]) == 1
        has_score = trace["iterations"][0].get("score") is not None
        check("TCR 1회 실행", has_iter)
        check("TCR score 반환", has_score, f"score={trace['iterations'][0].get('score')}")
        check("TCR 번역문 한국어", any('\uAC00' <= c <= '\uD7A3' for c in ko), ko[:50])
    except Exception as e:
        check("TCR Loop 실행", False, str(e))


# ──────────────────────────────────────────────
# 최종 결과
# ──────────────────────────────────────────────
section("최종 결과")

total  = len(results)
passed = sum(1 for _, r in results if r)
failed = total - passed

print(f"\n  검증 항목: {total}개")
print(f"  {PASS} 통과: {passed}개")
if failed:
    print(f"  {FAIL} 실패: {failed}개")
    for name, r in results:
        if not r:
            print(f"       ✗ {name}")
else:
    print(f"\n  모든 검증 통과!")

# DB 정리
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

sys.exit(0 if failed == 0 else 1)
