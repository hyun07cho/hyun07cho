"""Claude가 편집자 역할: 사용자 지시문 + 분석 결과 → EditPlan(JSON)."""

from __future__ import annotations

import json
import os

import anthropic

from .plan import Analysis, EditPlan, normalize

DEFAULT_MODEL = "claude-opus-5"

SYSTEM_PROMPT = """당신은 숙련된 유튜브/브이로그 영상 편집자입니다.
사용자의 편집 지시문과 영상 분석 데이터(무음 구간, 말한 내용의 타임스탬프, 사용 가능한 효과음 목록)를 보고
프리미어 프로에 그대로 들어갈 편집 계획을 JSON으로 만듭니다.

규칙:
- 모든 시간은 원본 영상 기준 초(source seconds)입니다. 잘라낸 뒤의 타임라인 시간이 아닙니다.
- keeps: 남길 구간. 시간순, 서로 겹치지 않게. 사용자가 "무음 잘라줘"류의 지시를 하면 speech 구간을 기본으로 쓰되,
  말 중간의 아주 짧은 쉼(0.5초 미만)은 자연스럽게 남겨도 됩니다. 컷 경계는 단어 중간을 자르지 마세요.
- captions: 자막은 transcript를 기반으로 하되, 한 줄에 너무 길지 않게(한국어 기준 20자 내외) 나누고 오타/군더더기("어", "음")는 정리합니다.
  사용자가 자막을 원하지 않으면 빈 리스트.
- sfx: 반드시 available_sfx 목록에 있는 이름만 사용합니다. 목록이 비어 있으면 빈 리스트.
  웃음, 강조, 전환, 반전 같은 포인트에 과하지 않게 배치합니다. keeps 안에 있는 시점만 사용하세요.
- summary: 무엇을 어떻게 편집했는지 사용자에게 한국어로 2~3문장.
- 사용자의 지시가 최우선입니다. 지시와 규칙이 충돌하면 지시를 따릅니다."""


def _analysis_payload(analysis: Analysis) -> dict:
    return {
        "duration_seconds": round(analysis.media.duration, 3),
        "fps": analysis.media.fps,
        "silences": [[round(s.start, 3), round(s.end, 3)] for s in analysis.silences],
        "speech": [[round(s.start, 3), round(s.end, 3)] for s in analysis.speech],
        "transcript": [
            {"start": round(t.start, 3), "end": round(t.end, 3), "text": t.text}
            for t in analysis.transcript
        ],
        "available_sfx": analysis.sfx_names,
    }


def build_user_message(analysis: Analysis, instruction: str) -> str:
    return (
        f"## 사용자 편집 지시\n{instruction.strip() or '(지시 없음: 무음 잘라내고 자막만 넣어줘)'}\n\n"
        f"## 영상 분석 데이터 (JSON)\n{json.dumps(_analysis_payload(analysis), ensure_ascii=False)}"
    )


def plan_with_claude(analysis: Analysis, instruction: str, model: str = DEFAULT_MODEL,
                     client: anthropic.Anthropic | None = None) -> EditPlan:
    """Claude에게 편집 계획을 받아온다. ANTHROPIC_API_KEY(또는 ant auth 프로필)가 필요."""
    client = client or anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(analysis, instruction)}],
        output_format=EditPlan,
        # 안전 분류기가 요청을 거절하면 서버가 같은 요청을 다른 모델로 이어서 처리
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        raise RuntimeError(f"모델이 요청을 거절했어요: {getattr(detail, 'explanation', '') or detail}")
    if response.parsed_output is None:
        raise RuntimeError("모델 응답을 EditPlan으로 파싱하지 못했어요.")
    return normalize(response.parsed_output, analysis.media.duration)


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_PROFILE"))
