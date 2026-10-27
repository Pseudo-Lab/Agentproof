# 데이터 확보

원본 데이터는 커밋하지 않는다. 아래 명령으로 `data/raw/` 에 받고 체크섬을 확인한다(`data/raw/` 는 git 제외).
실험 폴더(`experiments/E03-common-benchmark-env/`)에서 실행한다.

| 파일 | 출처 · 버전 | 문항 | 사용 조건 | SHA-256 |
|---|---|---|---|---|
| `locomo10.json` | [snap-research/locomo](https://github.com/snap-research/locomo) `data/locomo10.json` @ `3eb6f2c` | 대화 10개, cat1–4 1,540문항 (cat5 446 기본 제외) | CC BY-NC 4.0 (비상업) | `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4` |
| `longmemeval_s_cleaned.json` | [xiaowu0162/longmemeval-cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) (2025-09 정리판) | 질문 500 | MIT ([LongMemEval](https://github.com/xiaowu0162/LongMemEval)) | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` |
| `longmemeval_oracle.json` | 같은 곳 | 질문 500 (근거 세션만, 배선 확인용) | 같음 | `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` |
| `longmemeval_m_cleaned.json` | 같은 곳 | 질문 500 (질문당 약 500세션) | 같음 | 미확인 (아직 받지 않음) |

체크섬은 2026-10-27 제출자가 로컬에 받은 파일로 계산했다. 같은 날 아래 URL 로 `locomo10.json`·`longmemeval_oracle.json` 을
다시 받아 체크섬이 일치함을 확인했다(`longmemeval_s_cleaned.json` 은 277MB 라 재다운로드 확인은 하지 않았다).

```sh
mkdir -p data/raw
curl -L -o data/raw/locomo10.json https://raw.githubusercontent.com/snap-research/locomo/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/data/locomo10.json
curl -L -o data/raw/longmemeval_s_cleaned.json https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json
curl -L -o data/raw/longmemeval_oracle.json https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_oracle.json
shasum -a 256 data/raw/*.json
```

분할: 두 벤치마크 모두 공개 테스트 세트 하나뿐이다. 파일럿에서 프롬프트·설정을 고르는 데 쓴 문항과
최종 평가 문항을 나누는 방법은 [CARD.md](../CARD.md) "설계 변경과 최종 태스크"에 정한다(미정).
