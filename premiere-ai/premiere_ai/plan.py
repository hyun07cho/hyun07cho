"""편집 계획(EditPlan) 스키마 + AI 없이도 동작하는 규칙 기반 플래너.

모든 시간은 **원본 영상 기준 초(source seconds)** 다. 타임라인 위치로의 변환은 export 단계에서 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from .media import MediaInfo, Segment
from .transcribe import TranscriptSegment


class Keep(BaseModel):
    """최종 영상에 남길 원본 구간."""
    start: float = Field(description="원본 기준 시작 초")
    end: float = Field(description="원본 기준 끝 초")
    reason: str = Field(description="왜 남기는지 한 줄")


class Caption(BaseModel):
    start: float = Field(description="원본 기준 시작 초")
    end: float = Field(description="원본 기준 끝 초")
    text: str = Field(description="화면에 보여줄 자막 (짧고 읽기 쉽게)")


class Sfx(BaseModel):
    at: float = Field(description="원본 기준 효과음 시작 초")
    name: str = Field(description="사용 가능한 효과음 이름 중 하나 (파일명, 확장자 제외)")
    reason: str = Field(description="왜 여기에 넣는지 한 줄")


class EditPlan(BaseModel):
    keeps: list[Keep] = Field(description="남길 구간들. 시간순, 겹치지 않게")
    captions: list[Caption] = Field(description="자막 목록")
    sfx: list[Sfx] = Field(description="효과음 배치 목록")
    summary: str = Field(description="편집 의도를 사용자에게 한국어로 2~3문장 설명")


@dataclass
class Analysis:
    """플래너에 넘겨주는 분석 결과 묶음."""
    media: MediaInfo
    silences: list[Segment]
    speech: list[Segment]
    transcript: list[TranscriptSegment] = field(default_factory=list)
    sfx_names: list[str] = field(default_factory=list)


def normalize(plan: EditPlan, duration: float, min_keep: float = 0.2) -> EditPlan:
    """AI/규칙이 만든 계획을 안전하게 정리: 범위 클램프, 정렬, 겹침 병합, 자막/효과음은 keep 안에 있는 것만."""
    keeps: list[Keep] = []
    for k in sorted(plan.keeps, key=lambda k: k.start):
        a, b = max(0.0, k.start), min(duration, k.end)
        if b - a < min_keep:
            continue
        if keeps and a <= keeps[-1].end:
            keeps[-1] = Keep(start=keeps[-1].start, end=max(keeps[-1].end, b), reason=keeps[-1].reason)
        else:
            keeps.append(Keep(start=a, end=b, reason=k.reason))

    def inside(t: float) -> bool:
        return any(k.start <= t <= k.end for k in keeps)

    captions: list[Caption] = []
    for c in sorted(plan.captions, key=lambda c: c.start):
        text = c.text.strip()
        if not text or c.end <= c.start:
            continue
        # 자막이 여러 keep에 걸치면 각 keep 안으로 잘라준다
        for k in keeps:
            a, b = max(c.start, k.start), min(c.end, k.end)
            if b - a > 0.05:
                captions.append(Caption(start=a, end=b, text=text))

    sfx = [s for s in sorted(plan.sfx, key=lambda s: s.at) if inside(s.at)]
    return EditPlan(keeps=keeps, captions=captions, sfx=sfx, summary=plan.summary)


def rule_based_plan(analysis: Analysis, instruction: str = "") -> EditPlan:
    """API 키 없이도 되는 기본 편집: 무음 잘라내기 + Whisper 자막 그대로."""
    keeps = [Keep(start=s.start, end=s.end, reason="소리 나는 구간") for s in analysis.speech]
    if not keeps:
        keeps = [Keep(start=0.0, end=analysis.media.duration, reason="무음 구간을 찾지 못해 전체 유지")]
    captions = [Caption(start=t.start, end=t.end, text=t.text) for t in analysis.transcript if t.text.strip()]
    removed = analysis.media.duration - sum(k.end - k.start for k in keeps)
    summary = f"무음 구간 {len(analysis.silences)}개를 잘라 약 {removed:.1f}초를 줄였어요. 자막 {len(captions)}개."
    if instruction:
        summary += " (규칙 기반 모드라 지시문은 반영되지 않았어요. AI 모드는 ANTHROPIC_API_KEY 설정 후 사용)"
    return normalize(EditPlan(keeps=keeps, captions=captions, sfx=[], summary=summary), analysis.media.duration)
