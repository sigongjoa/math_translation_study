#!/usr/bin/env python3
import sys
import os
import json
from pathlib import Path

# 1. sys.path에 src 추가
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent.parent
src_path = str(project_root / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# 2. WSDAgent import (에러 처리 포함)
try:
    from pcm.core.wsd_agent import WSDAgent
except ImportError as e:
    print(f"Error: WSDAgent 로드 실패. PYTHONPATH를 확인하세요. ({e})")
    sys.exit(1)

def generate_demo():
    # 경로 설정
    json_path = project_root / "seven_sketches" / "parsed_sections.json"
    report_path = "/tmp/wsd_demo_report.html"
    
    if not json_path.exists():
        print(f"Error: 파일을 찾을 수 없습니다: {json_path}")
        return

    # 데이터 로드
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 구조에 맞게 sections 리스트 추출
    sections_list = data.get('sections', [])

    target_ids = ['1.1', '1.1.1', '1.1.2']
    target_sections = [s for s in sections_list if s.get('section_id') in target_ids]
    
    if not target_sections:
        print(f"Warning: 대상 섹션({target_ids})을 찾지 못했습니다. ID 형식을 확인하세요.")
        # 데이터 구조 확인을 위해 첫 3개라도 시도
        target_sections = sections_list[:3]

    agent = WSDAgent()
    results = []

    print(f"--- WSD Agent 분석 시작 (대상 섹션: {len(target_sections)}개) ---")

    for sec in target_sections:
        section_id = sec.get('section_id', 'N/A')
        title = sec.get('title_original', 'Untitled')
        content = sec.get('content_original', '')
        translated = sec.get('content_translated', '번역 데이터 없음')

        # WSD 분석 수행
        analysis = agent.analyze(content)
        
        domain = analysis.get('domain', 'general')
        terms = analysis.get('guide', {}).get('terms', [])
        prompt_injection = analysis.get('prompt_injection', '')

        results.append({
            'id': section_id,
            'title': title,
            'content_original': content,
            'content_translated': translated,
            'domain': domain,
            'terms': terms,
            'prompt_injection': prompt_injection
        })

        # 콘솔 출력
        print(f"[{section_id}] {title}")
        print(f"  - Detected Domain: {domain}")
        print(f"  - Found Terms: {len(terms)} items")
        print("-" * 30)

    # HTML 리포트 생성
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WSD Agent 통합 데모 - Seven Sketches</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background-color: #f8f9fa; padding-top: 2rem; padding-bottom: 4rem; }}
        .section-card {{ margin-bottom: 2.5rem; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: none; overflow: hidden; }}
        .card-header-custom {{ background-color: #2c3e50; color: white; padding: 1rem 1.5rem; }}
        .panel-title {{ font-weight: 600; font-size: 0.9rem; text-transform: uppercase; color: #6c757d; margin-bottom: 1rem; border-bottom: 2px solid #eee; padding-bottom: 0.5rem; }}
        .content-box {{ height: 400px; overflow-y: auto; font-size: 0.95rem; line-height: 1.6; background: white; padding: 1rem; border: 1px solid #dee2e6; border-radius: 4px; }}
        pre {{ background: #f1f3f5; padding: 1rem; border-radius: 4px; font-size: 0.85rem; border-left: 4px solid #0d6efd; white-space: pre-wrap; }}
        .domain-badge {{ font-size: 0.8rem; vertical-align: middle; }}
        .term-table {{ font-size: 0.85rem; }}
        .term-table th {{ background-color: #f8f9fa; }}
    </style>
</head>
<body>
<div class="container-fluid px-5">
    <header class="mb-5 text-center">
        <h1 class="display-5 fw-bold">WSD Agent 통합 데모</h1>
        <p class="lead text-muted">Seven Sketches in Compositionality - 다의어 보정 프롬프트 주입 효과 시각화</p>
        <hr class="w-25 mx-auto">
    </header>

    <div class="row">
"""

    for res in results:
        terms_html = ""
        if res['terms']:
            terms_rows = ""
            for t in res['terms']:
                terms_rows += f"<tr><td><code>{t['term']}</code></td><td><strong>{t['translation']}</strong></td><td>{res['domain']}</td></tr>"
            
            terms_html = f"""
            <div class="panel-title mt-3">감지된 다의어 용어</div>
            <table class="table table-sm term-table table-bordered">
                <thead><tr><th>영어 용어</th><th>권장 번역(KO)</th><th>도메인</th></tr></thead>
                <tbody>{terms_rows}</tbody>
            </table>
            """
        else:
            terms_html = "<div class='alert alert-light border text-muted'>감지된 특수 용어 없음</div>"

        html_content += f"""
        <!-- Section {res['id']} -->
        <div class="col-12">
            <div class="card section-card">
                <div class="card-header-custom d-flex justify-content-between align-items-center">
                    <h3 class="mb-0 h5">섹션 {res['id']}: {res['title']}</h3>
                    <span class="badge bg-primary domain-badge">Domain: {res['domain'].upper()}</span>
                </div>
                <div class="card-body">
                    <div class="row g-4">
                        <!-- Panel 1: Original -->
                        <div class="col-md-4">
                            <div class="panel-title">Panel 1: 원문 (영어)</div>
                            <div class="content-box">
                                {res['content_original'][:500].replace('<', '&lt;').replace('>', '&gt;')}...
                            </div>
                        </div>
                        
                        <!-- Panel 2: WSD Analysis -->
                        <div class="col-md-4">
                            <div class="panel-title">Panel 2: WSD 분석</div>
                            <div class="mb-3">
                                <small class="text-muted d-block mb-2">분석 결과 주입될 프롬프트 예시:</small>
                                <pre>{res['prompt_injection']}</pre>
                            </div>
                            {terms_html}
                        </div>

                        <!-- Panel 3: Translation -->
                        <div class="col-md-4">
                            <div class="panel-title">Panel 3: 기존 번역 (Baseline)</div>
                            <div class="content-box bg-light">
                                {res['content_translated'][:500]}...
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """

    html_content += """
    </div>
</div>
<footer class="text-center text-muted mt-5">
    <p>&copy; 2026 PCM Translation Pipeline - WSD Agent Demo</p>
</footer>
</body>
</html>
"""

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"\n[성공] 리포트 저장됨: {report_path}")

if __name__ == "__main__":
    generate_demo()
