"""ffmpeg/ffprobe 래퍼: 영상 정보 읽기, 무음 구간 감지, 말하는 구간 계산."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MediaInfo:
    path: str
    duration: float          # 초
    fps: float
    width: int
    height: int
    audio_channels: int = 2
    sample_rate: int = 48000


@dataclass
class Segment:
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


def ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("ffmpeg를 찾을 수 없어요. ffmpeg를 설치하거나 `pip install imageio-ffmpeg` 하세요.") from e


def ffprobe_bin() -> str | None:
    return shutil.which("ffprobe")


def _parse_fps(text: str) -> float:
    # "30000/1001" 또는 "30/1" 또는 "29.97"
    if "/" in text:
        num, den = text.split("/", 1)
        den_f = float(den) if float(den) else 1.0
        return float(num) / den_f
    return float(text)


def probe(path: str | Path) -> MediaInfo:
    """ffprobe가 있으면 JSON으로, 없으면 `ffmpeg -i` 출력 파싱으로 정보를 얻는다."""
    path = str(path)
    probe_bin = ffprobe_bin()
    if probe_bin:
        out = subprocess.run(
            [probe_bin, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, check=True,
        ).stdout
        data = json.loads(out)
        video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
        audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
        duration = float(data["format"].get("duration") or (video or {}).get("duration") or 0.0)
        fps = _parse_fps(video["r_frame_rate"]) if video else 30.0
        return MediaInfo(
            path=path,
            duration=duration,
            fps=fps,
            width=int(video["width"]) if video else 1920,
            height=int(video["height"]) if video else 1080,
            audio_channels=int(audio.get("channels", 2)) if audio else 0,
            sample_rate=int(audio.get("sample_rate", 48000)) if audio else 48000,
        )
    return _probe_with_ffmpeg(path)


def _probe_with_ffmpeg(path: str) -> MediaInfo:
    err = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    duration = 0.0
    if m:
        h, mnt, s = m.groups()
        duration = int(h) * 3600 + int(mnt) * 60 + float(s)
    vm = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", err)
    width, height = (int(vm.group(1)), int(vm.group(2))) if vm else (1920, 1080)
    fm = re.search(r"(\d+(?:\.\d+)?)\s*fps", err)
    fps = float(fm.group(1)) if fm else 30.0
    am = re.search(r"Audio:.*?(\d+)\s*Hz,\s*(mono|stereo|(\d+)\.?\d*\s*channels?|\d+ channels)", err)
    channels, rate = 0, 48000
    if am:
        rate = int(am.group(1))
        layout = am.group(2)
        channels = 1 if layout == "mono" else 2 if layout == "stereo" else int(re.search(r"\d+", layout).group())
    return MediaInfo(path=path, duration=duration, fps=fps, width=width, height=height,
                     audio_channels=channels, sample_rate=rate)


def detect_silence(path: str | Path, noise_db: float = -35.0, min_duration: float = 0.4,
                   total_duration: float | None = None) -> list[Segment]:
    """ffmpeg silencedetect 필터로 무음 구간을 찾는다."""
    cmd = [
        ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null", "-",
    ]
    err = subprocess.run(cmd, capture_output=True, text=True).stderr
    silences: list[Segment] = []
    start: float | None = None
    for line in err.splitlines():
        ms = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if ms:
            start = max(0.0, float(ms.group(1)))
            continue
        me = re.search(r"silence_end:\s*([\d.]+)", line)
        if me and start is not None:
            silences.append(Segment(start, float(me.group(1))))
            start = None
    if start is not None and total_duration is not None and total_duration > start:
        silences.append(Segment(start, total_duration))  # 끝까지 무음
    return silences


def speech_segments(duration: float, silences: list[Segment], pad: float = 0.12,
                    min_length: float = 0.25) -> list[Segment]:
    """무음의 보집합 = 소리 나는 구간. 컷 경계가 너무 딱 붙지 않게 pad를 준다."""
    segs: list[Segment] = []
    cursor = 0.0
    for s in sorted(silences, key=lambda x: x.start):
        if s.start > cursor:
            segs.append(Segment(cursor, s.start))
        cursor = max(cursor, s.end)
    if cursor < duration:
        segs.append(Segment(cursor, duration))

    padded: list[Segment] = []
    for s in segs:
        a, b = max(0.0, s.start - pad), min(duration, s.end + pad)
        if b - a < min_length:
            continue
        if padded and a <= padded[-1].end:
            padded[-1] = Segment(padded[-1].start, max(padded[-1].end, b))
        else:
            padded.append(Segment(a, b))
    return padded
