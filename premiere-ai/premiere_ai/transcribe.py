"""faster-whisper로 음성 → 타임스탬프 있는 자막 텍스트. (선택 의존성)"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


def transcribe(path: str | Path, model_size: str = "small", language: str | None = None,
               device: str = "auto") -> list[TranscriptSegment]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "자막 생성에는 faster-whisper가 필요해요: `pip install faster-whisper` "
            "(자막 없이 컷만 하려면 --no-transcribe)"
        ) from e

    model = WhisperModel(model_size, device=device, compute_type="auto")
    segments, _info = model.transcribe(str(path), language=language, word_timestamps=True, vad_filter=True)
    out: list[TranscriptSegment] = []
    for seg in segments:
        words = [Word(w.start, w.end, w.word.strip()) for w in (seg.words or [])]
        out.append(TranscriptSegment(seg.start, seg.end, seg.text.strip(), words))
    return out
