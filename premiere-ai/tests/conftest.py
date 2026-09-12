import subprocess
from pathlib import Path

import pytest

from premiere_ai.media import ffmpeg_bin


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    """6초짜리 테스트 영상: 0-2s 소리, 2-4s 무음, 4-6s 소리."""
    out = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run([
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:r=30:d=6",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
        "-af", "volume=enable='between(t,2,4)':volume=0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", "-shortest", str(out),
    ], check=True)
    return out


@pytest.fixture(scope="session")
def sfx_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("sfx")
    subprocess.run([
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=0.5", str(d / "ding.wav"),
    ], check=True)
    return d
