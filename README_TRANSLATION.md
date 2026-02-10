# 번역 실행 가이드 (페이지 76-100)

## 현재 상태

✅ **번역 진행 중!**
- 프로세스 ID: 26598
- 페이지 범위: 76-100 (총 25페이지)
- 섹션 수: 18개
- 로그 파일: `translation.log`

## 진행 상황 확인 방법

### 1. 진행 상황 스크립트 실행
```bash
./check_progress.sh
```

### 2. 실시간 로그 모니터링
```bash
tail -f translation.log
```

### 3. 완료된 섹션 확인
```bash
ls -lh output/sections/
```

## 예상 소요 시간

- **총 예상 시간**: 25-30분
- **섹션당 평균**: 1.5-2분
- **18개 섹션** 처리 필요

## 번역 완료 후 PDF 생성

번역이 완료되면 다음 명령으로 PDF를 생성하세요:

```bash
python3 generate_pdf.py --sections-dir output/sections --output translated_pages_76-100.pdf
```

## 문제 해결

### 번역이 멈춘 것 같다면
```bash
# 프로세스 확인
ps aux | grep translate_pipeline

# 로그 확인
tail -50 translation.log
```

### 다시 시작하려면
```bash
# 기존 프로세스 종료
pkill -f translate_pipeline

# 출력 폴더 초기화
rm -rf output && mkdir -p output

# 번역 재시작
nohup python3 translate_pipeline.py --start-page 75 --end-page 100 > translation.log 2>&1 &
```

## 완료 확인

번역이 완료되면 `translation.log`에 다음과 같은 메시지가 표시됩니다:
```
✅ Translation pipeline complete!
```

그리고 `output/sections/` 디렉토리에 18개의 JSON 파일이 생성됩니다.
