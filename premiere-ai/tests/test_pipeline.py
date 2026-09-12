import json
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from premiere_ai import brain, media
from premiere_ai.cli import main
from premiere_ai.export import source_to_timeline, timeline_captions, write_srt, write_xmeml
from premiere_ai.plan import Analysis, Caption, EditPlan, Keep, Sfx, normalize, rule_based_plan
from premiere_ai.sfx import index_sfx
from premiere_ai.transcribe import TranscriptSegment


def test_probe_and_silence(sample_video):
    info = media.probe(sample_video)
    assert 5.8 <= info.duration <= 6.2
    assert info.fps == pytest.approx(30, abs=0.1)
    assert (info.width, info.height) == (320, 240)
    assert info.audio_channels == 2

    silences = media.detect_silence(sample_video, total_duration=info.duration)
    assert len(silences) == 1
    assert silences[0].start == pytest.approx(2.0, abs=0.15)
    assert silences[0].end == pytest.approx(4.0, abs=0.15)

    speech = media.speech_segments(info.duration, silences)
    assert len(speech) == 2
    assert speech[0].start == 0.0 and speech[1].end == pytest.approx(info.duration)


def test_rule_plan_and_normalize(sample_video):
    info = media.probe(sample_video)
    silences = media.detect_silence(sample_video, total_duration=info.duration)
    speech = media.speech_segments(info.duration, silences)
    transcript = [TranscriptSegment(0.2, 1.8, "안녕하세요"), TranscriptSegment(1.5, 4.5, "무음에 걸친 자막")]
    plan = rule_based_plan(Analysis(info, silences, speech, transcript), "")
    assert len(plan.keeps) == 2
    # 두 번째 자막은 무음(2~4s)에 걸쳐 있으므로 두 keep으로 잘려 들어간다
    texts = [c.text for c in plan.captions]
    assert texts.count("무음에 걸친 자막") == 2
    assert plan.sfx == []


def test_normalize_merges_and_clamps():
    raw = EditPlan(
        keeps=[Keep(start=5, end=9, reason=""), Keep(start=-1, end=3, reason=""), Keep(start=2.5, end=4, reason=""),
               Keep(start=9.5, end=9.55, reason="tiny"), Keep(start=8, end=20, reason="")],
        captions=[Caption(start=1, end=2, text="  a "), Caption(start=1, end=2, text="  ")],
        sfx=[Sfx(at=3.5, name="ding", reason=""), Sfx(at=4.5, name="ding", reason="cut out")],
        summary="s",
    )
    plan = normalize(raw, duration=10)
    assert [(k.start, k.end) for k in plan.keeps] == [(0, 4), (5, 10)]
    assert [c.text for c in plan.captions] == ["a"]
    assert [s.at for s in plan.sfx] == [3.5]


def test_source_to_timeline():
    keeps = [Keep(start=1, end=3, reason=""), Keep(start=5, end=6, reason="")]
    assert source_to_timeline(1.0, keeps) == 0.0
    assert source_to_timeline(2.5, keeps) == 1.5
    assert source_to_timeline(5.5, keeps) == 2.5
    assert source_to_timeline(4.0, keeps) is None


def test_srt(tmp_path):
    p = write_srt([Caption(start=0.5, end=1.25, text="hi")], tmp_path / "a.srt")
    assert p.read_text(encoding="utf-8") == "1\n00:00:00,500 --> 00:00:01,250\nhi\n"


def test_xmeml_structure(sample_video, sfx_dir, tmp_path):
    info = media.probe(sample_video)
    plan = EditPlan(
        keeps=[Keep(start=0, end=2, reason=""), Keep(start=4, end=6, reason="")],
        captions=[], sfx=[Sfx(at=4.5, name="ding", reason="")], summary="",
    )
    out = write_xmeml(plan, info, tmp_path / "seq.xml", index_sfx(sfx_dir))
    text = out.read_text(encoding="utf-8")
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>')
    root = ET.fromstring(text.split("\n", 2)[2])
    seq = root.find("sequence")
    assert seq.findtext("duration") == "120"          # 4초 * 30fps
    vclips = seq.findall("media/video/track/clipitem")
    assert len(vclips) == 2
    assert [c.findtext("start") for c in vclips] == ["0", "60"]
    assert [c.findtext("end") for c in vclips] == ["60", "120"]
    assert [(c.findtext("in"), c.findtext("out")) for c in vclips] == [("0", "60"), ("120", "180")]
    # 원본 파일은 한 번만 완전 정의, 이후엔 id 참조
    files = root.iter("file")
    defined = [f for f in files if f.find("pathurl") is not None]
    assert len(defined) == 2                            # 원본 + ding.wav
    assert defined[0].findtext("pathurl").startswith("file://localhost/")
    atracks = seq.findall("media/audio/track")
    assert len(atracks) == 3                            # 스테레오 2트랙 + 효과음 1트랙
    sfx_clip = atracks[2].find("clipitem")
    assert sfx_clip.findtext("start") == "75"           # 원본 4.5s → 타임라인 2.5s → 75프레임
    # 비디오 클립이 오디오 2개와 링크됨
    assert len(vclips[0].findall("link")) == 3


def test_brain_prompt_and_parse(sample_video, monkeypatch):
    info = media.probe(sample_video)
    analysis = Analysis(info, [media.Segment(2, 4)], [media.Segment(0, 2), media.Segment(4, 6)],
                        [TranscriptSegment(0.2, 1.8, "안녕")], ["ding"])
    msg = brain.build_user_message(analysis, "무음 잘라줘")
    assert "무음 잘라줘" in msg and '"available_sfx": ["ding"]' in msg

    fake_plan = EditPlan(keeps=[Keep(start=0, end=2, reason="r"), Keep(start=4, end=7, reason="r")],
                         captions=[Caption(start=0.2, end=1.8, text="안녕")], sfx=[Sfx(at=4.5, name="ding", reason="")],
                         summary="ok")
    captured = {}

    def fake_parse(**kw):
        captured.update(kw)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=fake_plan)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=fake_parse)))
    plan = brain.plan_with_claude(analysis, "무음 잘라줘", client=client)
    assert captured["model"] == "claude-opus-5" and captured["output_format"] is EditPlan
    assert captured["fallbacks"] == "default"
    assert plan.keeps[-1].end == pytest.approx(info.duration)   # 7초 → 영상 길이로 클램프


def test_cli_edit_no_ai(sample_video, sfx_dir, tmp_path, capsys):
    rc = main(["edit", str(sample_video), "--no-ai", "--no-transcribe", "--sfx-dir", str(sfx_dir),
               "--out-dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "sample_ai_edit.xml").exists()
    assert (tmp_path / "sample_ai_captions.srt").exists()
    plan = json.loads((tmp_path / "sample_ai_plan.json").read_text(encoding="utf-8"))
    assert len(plan["keeps"]) == 2
    assert "줄였어요" in capsys.readouterr().err
