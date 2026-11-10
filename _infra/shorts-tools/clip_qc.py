#!/usr/bin/env python3
"""클립 자동 검사 + 6프레임 시트.

수치로 잡는 것: 길이·fps·해상도·오디오 유무, 컷 수(장면 점수 0.3 / 0.15 / 프레임 차 급등 중 최대),
첫 1초 움직임(앞쪽 정지), 첫 프레임 대비 색 이탈, 끝 프레임 편차.
수치로 못 잡는 것(모핑, 두 번째 개체, 글자 생성)은 시트(_qc.jpg)를 눈으로 본다.

사용: python3 _infra/shorts-tools/clip_qc.py <clip.mp4> [--expect-cuts N] [--sheet out.jpg]
ffmpeg/ffprobe만 호출한다(네트워크·설치 없음).
"""
import argparse
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

SMALL_W, SMALL_H = 72, 128


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    if r.returncode != 0:
        raise SystemExit(f"ffprobe 실패: {r.stderr.strip()}")
    j = json.loads(r.stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    num, den = (v.get("avg_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    return {"duration": float(j["format"].get("duration", 0)), "fps": round(fps, 3),
            "width": v["width"], "height": v["height"], "has_audio": a is not None,
            "nb_frames": int(v.get("nb_frames", 0) or 0)}


def scene_cuts(path, thr):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-an", "-vf",
             f"select='gt(scene,{thr})',showinfo", "-f", "null", "-"])
    return len(re.findall(r"pts_time:", r.stderr))


def small_frames(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf",
                        f"scale={SMALL_W}:{SMALL_H}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                       capture_output=True, check=False)
    buf = np.frombuffer(r.stdout, dtype=np.uint8)
    n = buf.size // (SMALL_W * SMALL_H * 3)
    return buf[: n * SMALL_W * SMALL_H * 3].reshape(n, SMALL_H, SMALL_W, 3).astype(np.float32)


def analyze(frames, fps):
    if len(frames) < 2:
        return {}
    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2, 3))
    med = float(np.median(diffs)) or 1e-6
    spikes = np.where((diffs > max(8.0, med * 6)))[0]
    # 인접 급등은 한 컷으로 묶는다
    cuts, last = [], -10
    for i in spikes:
        if i - last > 3:
            cuts.append(int(i) + 1)
        last = i
    first_n = max(1, int(round(fps)))
    first_motion = float(diffs[:first_n].mean())
    moving = np.where(diffs > max(0.6, med * 0.5))[0]
    motion_end = float((moving[-1] + 1) / fps) if len(moving) else 0.0
    first_mean = frames[0].mean(axis=(0, 1))
    last_mean = frames[-1].mean(axis=(0, 1))
    color_drift = float(np.abs(last_mean - first_mean).max())
    end_dev = float(np.abs(frames[-1] - frames[0]).mean())
    return {"framediff_cuts": len(cuts), "cut_frames": cuts,
            "first_second_motion": round(first_motion, 2),
            "frozen_start": first_motion < 0.3,
            "motion_end_s": round(motion_end, 2),
            "color_drift": round(color_drift, 1), "end_frame_dev": round(end_dev, 1)}


def sheet(path, duration, out):
    tiles = []
    for k in range(6):
        t = duration * (k + 0.5) / 6
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                            "-vf", "scale=270:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                           capture_output=True, check=False)
        if r.stdout:
            from io import BytesIO
            im = Image.open(BytesIO(r.stdout)).convert("RGB")
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, 70, 22], fill=(0, 0, 0))
            d.text((4, 4), f"{t:.2f}s", fill=(255, 255, 255))
            tiles.append(im)
    if not tiles:
        return None
    w, h = tiles[0].size
    canvas = Image.new("RGB", (w * 3, h * 2), (20, 20, 20))
    for i, im in enumerate(tiles):
        canvas.paste(im, ((i % 3) * w, (i // 3) * h))
    canvas.save(out, quality=88)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--expect-cuts", type=int, default=None, help="기대 컷 경계 수 (샷 수 - 1)")
    ap.add_argument("--sheet", default=None)
    a = ap.parse_args(argv)
    if not os.path.isfile(a.clip):
        raise SystemExit(f"파일 없음: {a.clip}")
    info = probe(a.clip)
    frames = small_frames(a.clip)
    res = {"clip": a.clip, **info, "decoded_frames": len(frames),
           "scene_cuts_0.3": scene_cuts(a.clip, 0.3), "scene_cuts_0.15": scene_cuts(a.clip, 0.15)}
    res.update(analyze(frames, info["fps"] or 24))
    res["cuts"] = max(res["scene_cuts_0.3"], res["scene_cuts_0.15"], res.get("framediff_cuts", 0))
    out = a.sheet or os.path.splitext(a.clip)[0] + "_qc.jpg"
    res["sheet"] = sheet(a.clip, info["duration"], out)
    flags = []
    if res.get("frozen_start"):
        flags.append("앞쪽 정지")
    if a.expect_cuts is not None and res["cuts"] < a.expect_cuts:
        flags.append(f"컷 부족 {res['cuts']}/{a.expect_cuts}")
    if res.get("color_drift", 0) > 25:
        flags.append("색 이탈 큼 (단일 샷이면 확인)")
    if not info["has_audio"]:
        flags.append("오디오 없음")
    res["flags"] = flags
    res["verdict"] = "CHECK" if flags else "PASS(수치)"
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
