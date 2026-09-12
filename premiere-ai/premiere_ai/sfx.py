"""효과음 라이브러리: 폴더 안의 오디오 파일을 이름(파일명)으로 찾는다."""

from __future__ import annotations

from pathlib import Path

AUDIO_EXT = {".wav", ".mp3", ".aif", ".aiff", ".m4a", ".ogg", ".flac"}


def index_sfx(sfx_dir: str | Path | None) -> dict[str, Path]:
    """{'ding': Path('sfx/ding.wav'), ...} — 키는 소문자 파일명(확장자 제외)."""
    if not sfx_dir:
        return {}
    root = Path(sfx_dir)
    if not root.is_dir():
        return {}
    index: dict[str, Path] = {}
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() in AUDIO_EXT:
            index.setdefault(p.stem.lower(), p)
    return index
