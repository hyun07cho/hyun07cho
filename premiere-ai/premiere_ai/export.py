"""EditPlan → 프리미어 프로가 import하는 FCP7 XML(xmeml) + SRT 자막."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import pathname2url

from .media import MediaInfo, probe
from .plan import Caption, EditPlan, Keep, Sfx


# ---------- 시간 변환 ----------

def source_to_timeline(t: float, keeps: list[Keep]) -> float | None:
    """원본 시각 t가 잘려나가지 않았다면 컷 이후 타임라인 시각을, 잘렸으면 None."""
    offset = 0.0
    for k in keeps:
        if k.start <= t <= k.end:
            return offset + (t - k.start)
        offset += k.end - k.start
    return None


def timeline_captions(plan: EditPlan) -> list[Caption]:
    out: list[Caption] = []
    for c in plan.captions:
        a = source_to_timeline(c.start, plan.keeps)
        b = source_to_timeline(c.end, plan.keeps)
        if a is None or b is None or b <= a:
            continue
        out.append(Caption(start=a, end=b, text=c.text))
    return out


# ---------- SRT ----------

def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(captions: list[Caption], out_path: str | Path) -> Path:
    lines: list[str] = []
    for i, c in enumerate(captions, 1):
        lines += [str(i), f"{_srt_time(c.start)} --> {_srt_time(c.end)}", c.text, ""]
    out_path = Path(out_path)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------- xmeml ----------

def _pathurl(path: str | Path) -> str:
    return "file://localhost" + pathname2url(str(Path(path).resolve()))


def _rate_el(parent: ET.Element, fps: float) -> ET.Element:
    timebase = int(round(fps))
    ntsc = "TRUE" if abs(fps - timebase) > 0.01 else "FALSE"
    rate = ET.SubElement(parent, "rate")
    ET.SubElement(rate, "timebase").text = str(timebase)
    ET.SubElement(rate, "ntsc").text = ntsc
    return rate


def _frames(seconds: float, fps: float) -> int:
    return int(round(seconds * fps))


class _XmemlBuilder:
    def __init__(self, media: MediaInfo, sequence_name: str):
        self.media = media
        self.fps = media.fps
        self.seq_name = sequence_name
        self._clip_id = 0
        self._file_ids: dict[str, str] = {}   # path -> file id
        self._file_defined: set[str] = set()

    def _next_clip_id(self) -> str:
        self._clip_id += 1
        return f"clipitem-{self._clip_id}"

    def _file_el(self, parent: ET.Element, info: MediaInfo, has_video: bool) -> None:
        """첫 등장 땐 전체 정의, 이후엔 id 참조만 (xmeml 규칙)."""
        fid = self._file_ids.setdefault(info.path, f"file-{len(self._file_ids) + 1}")
        f = ET.SubElement(parent, "file", id=fid)
        if fid in self._file_defined:
            return
        self._file_defined.add(fid)
        ET.SubElement(f, "name").text = Path(info.path).name
        ET.SubElement(f, "pathurl").text = _pathurl(info.path)
        _rate_el(f, self.fps)
        ET.SubElement(f, "duration").text = str(_frames(info.duration, self.fps))
        tc = ET.SubElement(f, "timecode")
        _rate_el(tc, self.fps)
        ET.SubElement(tc, "string").text = "00:00:00:00"
        ET.SubElement(tc, "frame").text = "0"
        ET.SubElement(tc, "displayformat").text = "NDF"
        m = ET.SubElement(f, "media")
        if has_video:
            v = ET.SubElement(m, "video")
            sc = ET.SubElement(v, "samplecharacteristics")
            _rate_el(sc, self.fps)
            ET.SubElement(sc, "width").text = str(info.width)
            ET.SubElement(sc, "height").text = str(info.height)
        if info.audio_channels:
            a = ET.SubElement(m, "audio")
            sc = ET.SubElement(a, "samplecharacteristics")
            ET.SubElement(sc, "depth").text = "16"
            ET.SubElement(sc, "samplerate").text = str(info.sample_rate)
            ET.SubElement(a, "channelcount").text = str(info.audio_channels)

    def _clipitem(self, track: ET.Element, info: MediaInfo, name: str, tl_start: float, tl_end: float,
                  src_in: float, src_out: float, mediatype: str, has_video: bool,
                  source_channel: int | None = None) -> tuple[str, ET.Element]:
        cid = self._next_clip_id()
        ci = ET.SubElement(track, "clipitem", id=cid)
        ET.SubElement(ci, "name").text = name
        ET.SubElement(ci, "enabled").text = "TRUE"
        ET.SubElement(ci, "duration").text = str(_frames(info.duration, self.fps))
        _rate_el(ci, self.fps)
        ET.SubElement(ci, "start").text = str(_frames(tl_start, self.fps))
        ET.SubElement(ci, "end").text = str(_frames(tl_end, self.fps))
        ET.SubElement(ci, "in").text = str(_frames(src_in, self.fps))
        ET.SubElement(ci, "out").text = str(_frames(src_out, self.fps))
        self._file_el(ci, info, has_video)
        if mediatype == "audio":
            st = ET.SubElement(ci, "sourcetrack")
            ET.SubElement(st, "mediatype").text = "audio"
            ET.SubElement(st, "trackindex").text = str(source_channel or 1)
        return cid, ci

    @staticmethod
    def _link(ci: ET.Element, members: list[tuple[str, str, int, int]]) -> None:
        """members: (clip id, mediatype, trackindex, clipindex)"""
        for cid, mtype, tidx, cidx in members:
            link = ET.SubElement(ci, "link")
            ET.SubElement(link, "linkclipref").text = cid
            ET.SubElement(link, "mediatype").text = mtype
            ET.SubElement(link, "trackindex").text = str(tidx)
            ET.SubElement(link, "clipindex").text = str(cidx)
            if mtype == "audio":
                ET.SubElement(link, "groupindex").text = "1"

    def build(self, plan: EditPlan, sfx_files: dict[str, Path]) -> ET.Element:
        media = self.media
        fps = self.fps
        total = sum(k.end - k.start for k in plan.keeps)

        root = ET.Element("xmeml", version="4")
        seq = ET.SubElement(root, "sequence", id="sequence-1")
        ET.SubElement(seq, "name").text = self.seq_name
        ET.SubElement(seq, "duration").text = str(_frames(total, fps))
        _rate_el(seq, fps)
        tc = ET.SubElement(seq, "timecode")
        _rate_el(tc, fps)
        ET.SubElement(tc, "string").text = "00:00:00:00"
        ET.SubElement(tc, "frame").text = "0"
        ET.SubElement(tc, "displayformat").text = "NDF"

        m = ET.SubElement(seq, "media")
        video = ET.SubElement(m, "video")
        fmt = ET.SubElement(video, "format")
        sc = ET.SubElement(fmt, "samplecharacteristics")
        _rate_el(sc, fps)
        ET.SubElement(sc, "width").text = str(media.width)
        ET.SubElement(sc, "height").text = str(media.height)
        ET.SubElement(sc, "pixelaspectratio").text = "square"
        ET.SubElement(sc, "fielddominance").text = "none"
        vtrack = ET.SubElement(video, "track")

        audio = ET.SubElement(m, "audio")
        ET.SubElement(audio, "numOutputChannels").text = "2"
        afmt = ET.SubElement(audio, "format")
        asc = ET.SubElement(afmt, "samplecharacteristics")
        ET.SubElement(asc, "depth").text = "16"
        ET.SubElement(asc, "samplerate").text = str(media.sample_rate)
        n_src_ch = max(1, media.audio_channels) if media.audio_channels else 0
        atracks = [ET.SubElement(audio, "track") for _ in range(n_src_ch)]

        # --- 컷 편집: keeps를 순서대로 타임라인에 이어붙임 ---
        cursor = 0.0
        src_name = Path(media.path).name
        for idx, k in enumerate(plan.keeps, 1):
            tl_start, tl_end = cursor, cursor + (k.end - k.start)
            vid, vel = self._clipitem(vtrack, media, src_name, tl_start, tl_end, k.start, k.end, "video", True)
            members = [(vid, "video", 1, idx)]
            aels: list[ET.Element] = []
            for ch in range(n_src_ch):
                aid, ael = self._clipitem(atracks[ch], media, src_name, tl_start, tl_end, k.start, k.end,
                                          "audio", True, source_channel=ch + 1)
                members.append((aid, "audio", ch + 1, idx))
                aels.append(ael)
            for el in [vel, *aels]:
                self._link(el, members)
            cursor = tl_end

        # --- 효과음: 별도 오디오 트랙 ---
        if plan.sfx:
            sfx_track = ET.SubElement(audio, "track")
            sfx_infos: dict[str, MediaInfo] = {}
            for i, s in enumerate(plan.sfx, 1):
                path = sfx_files.get(s.name.lower())
                if path is None:
                    continue
                tl_at = source_to_timeline(s.at, plan.keeps)
                if tl_at is None:
                    continue
                info = sfx_infos.get(str(path))
                if info is None:
                    try:
                        info = probe(path)
                    except Exception:  # 파일이 이상해도 계획 전체를 죽이지 않는다
                        info = MediaInfo(path=str(path), duration=1.0, fps=fps, width=0, height=0,
                                         audio_channels=1)
                    info.fps = fps
                    sfx_infos[str(path)] = info
                length = info.duration if info.duration > 0 else 1.0
                self._clipitem(sfx_track, info, path.name, tl_at, tl_at + length, 0.0, length,
                               "audio", False, source_channel=1)
        return root


def write_xmeml(plan: EditPlan, media: MediaInfo, out_path: str | Path, sfx_files: dict[str, Path] | None = None,
                sequence_name: str | None = None) -> Path:
    name = sequence_name or f"{Path(media.path).stem}_ai_edit"
    root = _XmemlBuilder(media, name).build(plan, sfx_files or {})
    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    out_path = Path(out_path)
    out_path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + body + "\n", encoding="utf-8")
    return out_path
