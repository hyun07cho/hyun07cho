# premiere-ai

한국어로 "무음 다 잘라내고, 자막 넣고, 웃긴 데 효과음 넣어줘" 라고 말하면
**프리미어 프로에 바로 import 되는 시퀀스(XML) + 자막(SRT)** 를 만들어주는 파이프라인.

```
영상.mp4
  │
  ├─ ffmpeg   : 무음 구간 감지, 프레임레이트/해상도 읽기
  ├─ Whisper  : 말한 내용 + 타임스탬프 (선택)
  ├─ Claude   : 지시문 + 분석 데이터 → 편집 계획(EditPlan JSON)
  │             · 어디를 남기고 자를지 (keeps)
  │             · 자막 텍스트/타이밍 (captions)
  │             · 효과음 위치 (sfx)
  └─ export   : 영상_ai_edit.xml (FCP7 xmeml) + 영상_ai_captions.srt + 영상_ai_plan.json
```

## 설치

```bash
cd premiere-ai
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .                    # 컷편집 + 효과음 + XML
pip install -e ".[subtitles]"       # + Whisper 자막 (faster-whisper, 처음 실행 시 모델 다운로드)
```

ffmpeg는 시스템에 없어도 `imageio-ffmpeg`가 같이 깔려서 바로 동작해요.

AI 모드를 쓰려면 API 키:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
```

## 사용법

```bash
# 1) 분석만 보기 (무음/말 구간/자막)
premiere-ai analyze vlog.mp4 --no-transcribe

# 2) 편집 계획 + 프리미어용 파일 생성
premiere-ai edit vlog.mp4 \
  -i "말 사이 빈 곳 다 잘라내고, 자막은 짧게 끊어서 넣고, 웃음 나는 부분에 laugh 효과음" \
  --sfx-dir sfx/ --language ko

# API 키 없이 규칙 기반(무음 컷 + 자막)만
premiere-ai edit vlog.mp4 --no-ai
```

결과물 3개가 영상 옆(또는 `--out-dir`)에 생겨요:

| 파일 | 프리미어에서 |
|---|---|
| `vlog_ai_edit.xml` | **File > Import** → 컷이 이미 끝난 시퀀스가 생김. 효과음은 A3 트랙에 배치됨 |
| `vlog_ai_captions.srt` | **File > Import** 후 시퀀스에 드래그 → 캡션 트랙 생성 |
| `vlog_ai_plan.json` | AI가 무엇을/왜 편집했는지 (keeps / captions / sfx / summary) |

XML 안의 경로는 절대경로라서, 영상 파일을 옮기지 않은 상태에서 import 하면 미디어가 자동으로 연결돼요.

## 효과음

`sfx/` 폴더에 `laugh.wav`, `ding.mp3`, `whoosh.wav`처럼 넣으면 파일명이 곧 효과음 이름이 되고,
AI는 그 이름 목록만 보고 배치합니다. (없는 이름은 자동으로 무시)

## 옵션

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--noise` | -35 | 무음 판정 dB. 배경소음이 크면 -30, 조용한 녹음이면 -40 |
| `--min-silence` | 0.4 | 이 길이(초) 이상만 무음으로 취급 |
| `--whisper-model` | small | tiny / base / small / medium / large-v3 (클수록 정확, 느림) |
| `--language` | 자동 | `ko`로 고정하면 한국어 인식 더 안정적 |
| `--model` | claude-opus-5 | 편집 계획 만드는 모델 |

## 구조

```
premiere_ai/
  media.py       ffmpeg/ffprobe: probe(), detect_silence(), speech_segments()
  transcribe.py  faster-whisper 래퍼
  plan.py        EditPlan 스키마(Pydantic) + normalize() + rule_based_plan()
  brain.py       Claude 호출 (structured outputs로 EditPlan을 바로 받음)
  export.py      EditPlan → xmeml(XML) / SRT, 원본시간→타임라인시간 변환
  sfx.py         효과음 폴더 인덱싱
  cli.py         analyze / edit 명령
tests/           ffmpeg로 합성한 6초 영상으로 전체 파이프라인 검증
```

핵심 설계 한 가지: **AI는 항상 "원본 영상 기준 초"로만 생각**하고, 컷 이후 타임라인 위치 계산은
`export.source_to_timeline()`이 한다. 그래서 AI가 자를 구간을 바꿔도 자막·효과음 위치가 자동으로 따라온다.

## 테스트

```bash
pip install -e ".[dev]" && pytest
```

## 로드맵

- [x] v0.1 — 무음 컷 + Whisper 자막 + 효과음 배치 → XML/SRT 내보내기 (지금)
- [ ] v0.2 — 프리미어 **UXP 패널**: 프리미어 안에서 지시문 입력 → 열려 있는 시퀀스에 바로 적용 (import 과정 생략)
- [ ] v0.3 — 장면 전환 감지(scene detection), 화면 속 텍스트/표정 인식으로 "웃긴 부분" 자동 판단
- [ ] v0.4 — 대화형 수정: "3번째 컷은 다시 살려줘", "자막 폰트 크게" → plan.json만 고쳐서 재내보내기
