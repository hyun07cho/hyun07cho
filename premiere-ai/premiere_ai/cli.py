"""명령줄 진입점.

  python -m premiere_ai edit video.mp4 -i "무음 다 잘라내고 자막 넣고 웃긴 부분에 효과음" --sfx-dir sfx/
  python -m premiere_ai analyze video.mp4
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import brain, media as media_mod
from .export import timeline_captions, write_srt, write_xmeml
from .plan import Analysis, EditPlan, rule_based_plan
from .sfx import index_sfx


def analyze(video: str, noise_db: float, min_silence: float, do_transcribe: bool,
            whisper_model: str, language: str | None, sfx_dir: str | None) -> tuple[Analysis, dict[str, Path]]:
    info = media_mod.probe(video)
    silences = media_mod.detect_silence(video, noise_db=noise_db, min_duration=min_silence,
                                        total_duration=info.duration)
    speech = media_mod.speech_segments(info.duration, silences)
    transcript = []
    if do_transcribe:
        from .transcribe import transcribe
        print(f"[transcribe] whisper '{whisper_model}' 실행 중... (처음엔 모델 다운로드로 오래 걸릴 수 있어요)", file=sys.stderr)
        transcript = transcribe(video, model_size=whisper_model, language=language)
    sfx_files = index_sfx(sfx_dir)
    return Analysis(media=info, silences=silences, speech=speech, transcript=transcript,
                    sfx_names=sorted(sfx_files)), sfx_files


def cmd_analyze(args: argparse.Namespace) -> int:
    analysis, _ = analyze(args.video, args.noise, args.min_silence, not args.no_transcribe,
                          args.whisper_model, args.language, args.sfx_dir)
    print(json.dumps({
        "media": asdict(analysis.media),
        "silences": [asdict(s) for s in analysis.silences],
        "speech": [asdict(s) for s in analysis.speech],
        "transcript": [{"start": t.start, "end": t.end, "text": t.text} for t in analysis.transcript],
        "sfx": analysis.sfx_names,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    video = Path(args.video)
    if not video.is_file():
        print(f"파일이 없어요: {video}", file=sys.stderr)
        return 2
    analysis, sfx_files = analyze(str(video), args.noise, args.min_silence, not args.no_transcribe,
                                  args.whisper_model, args.language, args.sfx_dir)
    print(f"[analyze] {analysis.media.duration:.1f}s, {analysis.media.fps:.3f}fps, "
          f"무음 {len(analysis.silences)}개, 말 구간 {len(analysis.speech)}개, 자막 {len(analysis.transcript)}개, "
          f"효과음 {len(sfx_files)}개", file=sys.stderr)

    use_ai = not args.no_ai and brain.has_credentials()
    if not args.no_ai and not use_ai:
        print("[plan] ANTHROPIC_API_KEY가 없어서 규칙 기반 모드로 진행해요.", file=sys.stderr)
    plan: EditPlan = (brain.plan_with_claude(analysis, args.instruction, model=args.model)
                      if use_ai else rule_based_plan(analysis, args.instruction))

    out_dir = Path(args.out_dir or video.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = video.stem
    xml_path = write_xmeml(plan, analysis.media, out_dir / f"{stem}_ai_edit.xml", sfx_files)
    srt_path = write_srt(timeline_captions(plan), out_dir / f"{stem}_ai_captions.srt")
    (out_dir / f"{stem}_ai_plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    kept = sum(k.end - k.start for k in plan.keeps)
    print(f"\n{plan.summary}\n", file=sys.stderr)
    print(f"[result] {analysis.media.duration:.1f}s → {kept:.1f}s, 컷 {len(plan.keeps)}개, "
          f"자막 {len(plan.captions)}개, 효과음 {len(plan.sfx)}개", file=sys.stderr)
    print(f"[files]  {xml_path}\n         {srt_path}", file=sys.stderr)
    print("[next]   프리미어: File > Import 로 XML을 열면 컷이 끝난 시퀀스가 생겨요. "
          "SRT도 같은 방법으로 넣고 캡션 트랙에 드래그하면 됩니다.", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="premiere-ai", description="자연어로 프리미어 컷편집·자막·효과음 자동화")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("video")
        sp.add_argument("--noise", type=float, default=-35.0, help="무음 판정 dB (기본 -35)")
        sp.add_argument("--min-silence", type=float, default=0.4, help="이 길이(초) 이상만 무음으로 (기본 0.4)")
        sp.add_argument("--no-transcribe", action="store_true", help="Whisper 자막 생성 생략")
        sp.add_argument("--whisper-model", default="small", help="tiny/base/small/medium/large-v3")
        sp.add_argument("--language", default=None, help="ko, en 등. 비우면 자동 감지")
        sp.add_argument("--sfx-dir", default=None, help="효과음 파일 폴더")

    a = sub.add_parser("analyze", help="분석 결과만 JSON으로 출력")
    common(a)
    a.set_defaults(func=cmd_analyze)

    e = sub.add_parser("edit", help="편집 계획 생성 + 프리미어 XML/SRT 저장")
    common(e)
    e.add_argument("-i", "--instruction", default="", help="편집 지시문 (한국어 OK)")
    e.add_argument("--out-dir", default=None)
    e.add_argument("--no-ai", action="store_true", help="Claude 없이 규칙 기반으로만")
    e.add_argument("--model", default=brain.DEFAULT_MODEL)
    e.set_defaults(func=cmd_edit)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
