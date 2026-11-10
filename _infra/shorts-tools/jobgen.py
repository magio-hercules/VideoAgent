#!/usr/bin/env python3
"""쇼츠 제작용 ComfyUI 작업 JSON 생성기.

원본·쇼츠 템플릿은 수정하지 않고, 사본에 값만 넣어 작업 파일을 만든다.
네트워크, subprocess, 설치를 하지 않는다. 표준 라이브러리만 사용한다.

사용 (작업 폴더 루트에서):
  python3 _infra/shorts-tools/jobgen.py r2v \
      --prompt-file productions/shorts/EP001/prompts/b01.txt \
      --refs productions/shorts/EP001/refs/EP001_style.png productions/shorts/EP001/refs/EP001_prop.png \
      --win-root "<connectedFolders의 Windows 경로>" \
      --sec 7.5 --seed 101 --mp 0.25 --prefix VideoAgent/EP001/b01 \
      --out productions/shorts/EP001/jobs/b01.json

  r2v 결과의 "upload_first" 목록(Windows 경로)을 comfy-mcp upload_file(overwrite=True)로
  ComfyUI input 폴더에 먼저 올린 뒤 제출한다. 레퍼런스 파일 이름은 작품 접두어를 붙여 고유하게 짓는다.

  python3 _infra/shorts-tools/jobgen.py still \
      --prompt-file productions/shorts/EP001/prompts/ref_style.txt \
      --w 768 --h 1344 --seed 101 --prefix VideoAgent/EP001/refs/style \
      --out productions/shorts/EP001/jobs/ref_style.json
"""
import argparse
import copy
import json
import os
import re
import sys

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
R2V_TEMPLATE = "library/workflows/h3-r2v-speedx6/shorts_r2v_9x16.json"
STILL_TEMPLATE = "library/workflows/still-zimage-turbo/original/image_z_image_turbo.json"
H3_MAX_FRAMES = 243
R2V_SECTIONS = ["subject_definitions:", "summary:", "retention_analysis:",
                "detailed_description:", "overall_soundscape:", "non_diegetic_music:"]
RATIOS = {"1:1", "4:5", "5:4", "3:4", "4:3", "2:3", "3:2", "16:9", "9:16",
          "16:10", "10:16", "21:9", "9:21"}
SAGE_CHOICES = {"disabled", "auto", "sageattn_qk_int8_pv_fp16_cuda",
                "sageattn_qk_int8_pv_fp16_triton", "sageattn_qk_int8_pv_fp8_cuda",
                "sageattn_qk_int8_pv_fp8_cuda++", "sageattn3", "sageattn3_per_block_mean"}


class JobError(Exception):
    pass


def rel_safe(rel):
    if not rel or "\\" in rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel) \
            or any(p == ".." for p in rel.split("/")):
        raise JobError(f"작업 폴더 기준 슬래시 상대경로만 허용: {rel!r}")
    full = os.path.realpath(os.path.join(ROOT, *rel.split("/")))
    if os.path.commonpath([full, ROOT]) != ROOT:
        raise JobError(f"작업 폴더 밖 경로: {rel!r}")
    return full


def h3_frames(sec):
    n = max(5, round(sec * 24))
    return n + (5 - n % 17) % 17


def load(rel):
    with open(rel_safe(rel), "r", encoding="utf-8") as f:
        return json.load(f)


def nodes_by_id(nodes):
    return {n["id"]: n for n in nodes}


def read_prompt(rel):
    with open(rel_safe(rel), "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        raise JobError("프롬프트가 비어 있음")
    return text


def write_job(obj, out_rel):
    out = rel_safe(out_rel)
    if os.path.exists(out):
        raise JobError(f"이미 있는 작업 파일은 덮어쓰지 않음: {out_rel}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def to_windows(win_root, rel):
    rel_safe(rel)
    if not os.path.isfile(rel_safe(rel)):
        raise JobError(f"레퍼런스 파일 없음: {rel}")
    return win_root.rstrip("\\/") + "\\" + rel.replace("/", "\\")


def build_r2v(a):
    frames = h3_frames(a.sec)
    if frames > H3_MAX_FRAMES:
        raise JobError(f"{a.sec}s → {frames}프레임: 12GB 상한 {H3_MAX_FRAMES}(10.125s) 초과")
    if a.ratio not in RATIOS:
        raise JobError(f"ratio는 {sorted(RATIOS)} 중 하나")
    if a.sage not in SAGE_CHOICES:
        raise JobError(f"sage는 {sorted(SAGE_CHOICES)} 중 하나")
    if not 1 <= len(a.refs) <= 9:
        raise JobError("레퍼런스 이미지는 1~9장")
    prompt = read_prompt(a.prompt_file)
    missing = [s for s in R2V_SECTIONS if s not in prompt]
    if missing:
        raise JobError(f"R2V 6개 섹션 누락: {missing}")
    tags = sorted(set(int(x) for x in re.findall(r"<Picture (\d+)>", prompt)))
    if tags and tags[-1] > len(a.refs):
        raise JobError(f"프롬프트가 <Picture {tags[-1]}>를 쓰지만 레퍼런스는 {len(a.refs)}장")
    w = copy.deepcopy(load(R2V_TEMPLATE))
    N = nodes_by_id(w["nodes"])
    N[141]["widgets_values"][0] = prompt
    # Deno 레퍼런스 로더는 ComfyUI input 폴더 기준 상대경로만 읽는다(절대경로 거부).
    # 레퍼런스는 upload_file로 input 루트에 올리고, 여기에는 파일 이름만 넣는다.
    uploads = [to_windows(a.win_root, r) for r in a.refs]
    names = [os.path.basename(r) for r in a.refs]
    if len(set(names)) != len(names):
        raise JobError(f"레퍼런스 파일 이름이 겹침: {names} — 작품 접두어를 붙여 고유하게")
    if any(not re.fullmatch(r"[A-Za-z0-9._-]+", n) for n in names):
        raise JobError(f"레퍼런스 파일 이름은 영문·숫자·._- 만: {names}")
    N[142]["widgets_values"][0] = "\n".join(names)
    N[132]["widgets_values"][0] = float(a.sec)
    N[129]["widgets_values"][0] = int(a.seed)
    N[129]["widgets_values"][1] = "fixed"
    N[145]["widgets_values"][1] = a.ratio
    N[145]["widgets_values"][2] = float(a.mp)
    N[144]["widgets_values"]["filename_prefix"] = a.prefix
    N[181]["widgets_values"][0] = a.sage
    N[192]["widgets_values"][8] = bool(a.verbose_sol)  # BlockSparseAttention verbose
    write_job(w, a.out)
    return {"kind": "r2v", "out": a.out, "frames": frames, "sec_effective": round(frames / 24, 3),
            "refs": names, "upload_first": uploads,
            "seed": a.seed, "mp": a.mp, "ratio": a.ratio, "sage": a.sage}


def build_still(a):
    prompt = read_prompt(a.prompt_file)
    w = copy.deepcopy(load(STILL_TEMPLATE))
    sub = w["definitions"]["subgraphs"][0]
    S = nodes_by_id(sub["nodes"])
    S[27]["widgets_values"][0] = prompt
    S[13]["widgets_values"][0] = int(a.w)
    S[13]["widgets_values"][1] = int(a.h)
    S[3]["widgets_values"][0] = int(a.seed)
    S[3]["widgets_values"][1] = "fixed"
    S[3]["widgets_values"][2] = int(a.steps)
    N = nodes_by_id(w["nodes"])
    N[9]["widgets_values"][0] = a.prefix
    write_job(w, a.out)
    return {"kind": "still", "out": a.out, "w": a.w, "h": a.h, "seed": a.seed, "steps": a.steps}


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    ap = argparse.ArgumentParser(description="쇼츠 ComfyUI 작업 JSON 생성기")
    sp = ap.add_subparsers(dest="kind", required=True)
    r = sp.add_parser("r2v", help="MiniMax H3 R2V (SpeedX6) 클립")
    r.add_argument("--prompt-file", required=True)
    r.add_argument("--refs", nargs="+", required=True, help="작업 폴더 기준 레퍼런스 이미지 (순서 = <Picture n>)")
    r.add_argument("--win-root", required=True, help="이 작업 폴더의 Windows 절대경로")
    r.add_argument("--sec", type=float, required=True)
    r.add_argument("--seed", type=int, required=True)
    r.add_argument("--mp", type=float, default=0.25, help="1단계 시작 메가픽셀 (최종은 가로세로 2배)")
    r.add_argument("--ratio", default="9:16")
    r.add_argument("--sage", default="disabled")
    r.add_argument("--verbose-sol", action="store_true")
    r.add_argument("--prefix", required=True)
    r.add_argument("--out", required=True)
    s = sp.add_parser("still", help="Z-Image Turbo 정지 컷·레퍼런스")
    s.add_argument("--prompt-file", required=True)
    s.add_argument("--w", type=int, default=768)
    s.add_argument("--h", type=int, default=1344)
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--steps", type=int, default=8)
    s.add_argument("--prefix", required=True)
    s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        res = build_r2v(a) if a.kind == "r2v" else build_still(a)
    except JobError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 2
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
