#!/usr/bin/env python3
"""Codex CLI 내장 이미지 생성(image_gen)으로 그림을 만들어 지정한 파일로 저장한다.

ChatGPT 계정으로 로그인한 Codex를 쓰므로 API 키가 필요 없다. 대신 ChatGPT 요금제
사용량을 쓴다 — 실행 전에 대표 승인을 받는다(→ craft/playbooks/gpt-image.md).

사용법은 같은 폴더 README.md. 표준 라이브러리만 쓴다.
종료 코드: 0 성공, 1 생성 실패(그림 없음), 2 사용법·환경 오류.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_TIMEOUT_PER_IMAGE = 300


class ToolError(Exception):
    """사용법·환경 오류 (종료 코드 2)."""


# ---------- Codex 실행 파일 찾기 ----------

def parse_version(text: str) -> tuple[int, int, int] | None:
    m = VERSION_RE.search(text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    return Path(env) if env else Path.home() / ".codex"


def candidate_paths() -> list[str]:
    """찾을 순서: CODEX_BIN → 데스크톱 앱에 들어 있는 CLI(최근 것부터) → PATH의 codex."""
    out: list[str] = []
    env = os.environ.get("CODEX_BIN")
    if env:
        out.append(env)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        found = glob.glob(os.path.join(local, "OpenAI", "Codex", "bin", "*", "codex.exe"))
        found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        out.extend(found)
    which = shutil.which("codex")
    if which:
        out.append(which)
    seen, uniq = set(), []
    for p in out:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def probe_version(path: str) -> tuple[int, int, int] | None:
    try:
        r = subprocess.run([path, "--version"], capture_output=True, timeout=30,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_version(r.stdout.decode("utf-8", "replace"))


def choose_codex(probed: list[tuple[str, tuple[int, int, int] | None]]) -> tuple[str, tuple[int, int, int]]:
    """버전을 읽은 후보 중 가장 높은 버전을 고른다. 같으면 앞 순서."""
    best = None
    for path, ver in probed:
        if ver is None:
            continue
        if best is None or ver > best[1]:
            best = (path, ver)
    if best is None:
        raise ToolError("실행할 수 있는 Codex CLI를 찾지 못했다. Codex 데스크톱 앱이나 CLI가 있어야 한다 "
                        "(설치·업데이트는 대표 승인 사항). 경로를 알면 CODEX_BIN 또는 --codex로 지정한다.")
    return best


def find_codex(explicit: str | None = None) -> tuple[str, tuple[int, int, int]]:
    paths = [explicit] if explicit else candidate_paths()
    return choose_codex([(p, probe_version(p)) for p in paths])


def image_feature_state(path: str) -> str:
    """`codex features list`에서 image_generation 줄을 돌려준다(없으면 빈 문자열)."""
    try:
        r = subprocess.run([path, "features", "list"], capture_output=True, timeout=30,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if line.split()[:1] == ["image_generation"]:
            return " ".join(line.split())
    return ""


# ---------- 요청 만들기 ----------

def target_paths(out: Path, count: int) -> list[Path]:
    """한 장이면 out 그대로, 여러 장이면 <이름>_v01, _v02 …"""
    if count == 1:
        return [out]
    return [out.with_name(f"{out.stem}_v{i:02d}{out.suffix}") for i in range(1, count + 1)]


def build_instruction(prompt: str, count: int, ref_count: int) -> str:
    lines = [
        f"Use the built-in image_gen tool to generate exactly {count} image(s) from the prompt below.",
        "One image_gen call per image. Do not retry a failed call.",
        "Do not run shell commands, do not create, move or modify any files, and do not use any other tool "
        "except reading your image generation skill instructions.",
        "Keep the prompt's meaning; do not add text, letters, logos or watermarks to the image.",
    ]
    if ref_count:
        lines.append(f"{ref_count} reference image(s) are attached. Match their art style, palette and "
                     "recurring characters; do not copy their composition unless the prompt says so.")
    lines += [
        "When finished, reply with exactly: DONE <number of images generated>.",
        "",
        "PROMPT:",
        "<<<",
        prompt.strip(),
        ">>>",
    ]
    return "\n".join(lines) + "\n"


def build_command(codex: str, workdir: str, refs: list[str], model: str | None = None) -> list[str]:
    cmd = [codex, "exec", "--enable", "image_generation", "-s", "read-only",
           "--skip-git-repo-check", "--json", "-C", workdir]
    if model:
        cmd += ["-m", model]
    for r in refs:
        cmd.append(f"--image={r}")
    cmd += ["--", "-"]  # 프롬프트는 표준입력으로 (긴 글·따옴표 문제 회피)
    return cmd


# ---------- 결과 읽기 ----------

def parse_events(text: str) -> dict:
    info = {"thread_id": None, "errors": [], "last_message": None, "failed": False}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "thread.started":
            info["thread_id"] = ev.get("thread_id")
        elif t == "error":
            info["errors"].append(str(ev.get("message", "")))
        elif t == "turn.failed":
            info["failed"] = True
            info["errors"].append(str((ev.get("error") or {}).get("message", "")))
        elif t == "item.completed":
            item = ev.get("item") or {}
            if item.get("type") == "agent_message":
                info["last_message"] = item.get("text")
    return info


def collect_images(home: Path, thread_id: str) -> list[Path]:
    d = home / "generated_images" / thread_id
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name))


def image_size(path: Path) -> tuple[int, int] | None:
    """PNG 크기만 읽는다(다른 형식은 None)."""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    return None


# ---------- 실행 ----------

def read_prompt(args) -> str:
    if args.prompt_file:
        text = Path(args.prompt_file).read_text(encoding="utf-8")
    else:
        text = args.prompt or ""
    if not text.strip():
        raise ToolError("프롬프트가 비어 있다 (--prompt 또는 --prompt-file).")
    return text


def run(args) -> dict:
    prompt = read_prompt(args)
    out = Path(args.out)
    if out.suffix.lower() != ".png":
        raise ToolError("--out은 .png 파일 경로여야 한다.")
    targets = target_paths(out, args.count)
    exists = [str(p) for p in targets if p.exists()]
    if exists:
        raise ToolError("이미 있는 파일은 덮어쓰지 않는다 — 새 이름(_v2 등)을 쓴다: " + ", ".join(exists))
    refs = []
    for r in args.ref or []:
        if not Path(r).is_file():
            raise ToolError(f"참조 그림이 없다: {r}")
        refs.append(str(Path(r).resolve()))

    codex, ver = find_codex(args.codex)
    instruction = build_instruction(prompt, args.count, len(refs))
    workdir = tempfile.mkdtemp(prefix="codex-imagegen-")
    cmd = build_command(codex, workdir, refs, args.model)
    summary = {"codex": codex, "codex_version": ".".join(map(str, ver)), "targets": [str(p) for p in targets],
               "refs": refs, "count": args.count}
    if args.dry_run:
        shutil.rmtree(workdir, ignore_errors=True)
        summary.update(status="dry_run", command=cmd, instruction=instruction)
        return summary

    timeout = args.timeout or DEFAULT_TIMEOUT_PER_IMAGE * args.count
    started = time.time()
    try:
        r = subprocess.run(cmd, input=instruction.encode("utf-8"), capture_output=True, timeout=timeout)
        events = r.stdout.decode("utf-8", "replace")
        rc = r.returncode
    except subprocess.TimeoutExpired as e:
        events = (e.stdout or b"").decode("utf-8", "replace")
        rc = "timeout"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    info = parse_events(events)
    summary.update(thread_id=info["thread_id"], exit=rc, seconds=round(time.time() - started),
                   message=info["last_message"], errors=[e for e in info["errors"] if e][:5])
    images = collect_images(codex_home(), info["thread_id"]) if info["thread_id"] else []
    if not images:
        summary["status"] = "failed"
        return summary

    saved = []
    for i, src in enumerate(images):
        dst = targets[i] if i < len(targets) else out.with_name(f"{out.stem}_v{i + 1:02d}{out.suffix}")
        if dst.exists():
            summary.setdefault("skipped", []).append(f"{src} → {dst} (이미 있음)")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        size = image_size(dst)
        saved.append({"file": str(dst), "source": str(src), "size": list(size) if size else None})
    summary["saved"] = saved
    summary["status"] = "ok" if len(saved) >= args.count else ("partial" if saved else "failed")
    return summary


def cmd_check(args) -> int:
    paths = [args.codex] if args.codex else candidate_paths()
    probed = [(p, probe_version(p)) for p in paths]
    for p, v in probed:
        print(f"  {'.'.join(map(str, v)) if v else '실행 불가':<12} {p}")
    try:
        codex, ver = choose_codex(probed)
    except ToolError as e:
        print(f"[오류] {e}")
        return 2
    feat = image_feature_state(codex) or "(image_generation 항목 없음)"
    print(f"선택: {codex} ({'.'.join(map(str, ver))})")
    print(f"기능: {feat}")
    print(f"저장 위치: {codex_home() / 'generated_images'}")
    return 0


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Codex CLI 내장 image_gen으로 그림 생성")
    ap.add_argument("--check", action="store_true", help="쓸 Codex와 기능 상태만 확인 (생성 안 함)")
    ap.add_argument("--prompt", help="프롬프트 문장")
    ap.add_argument("--prompt-file", help="프롬프트 파일 (UTF-8)")
    ap.add_argument("--ref", action="append", help="참조 그림 (여러 번 가능)")
    ap.add_argument("--out", help="저장할 .png 경로. 여러 장이면 _v01, _v02 …")
    ap.add_argument("--count", type=int, default=1, help="장수 (기본 1, 최대 4)")
    ap.add_argument("--codex", help="Codex 실행 파일 경로 (기본: 자동 선택)")
    ap.add_argument("--model", help="Codex 모델 (기본: Codex 설정)")
    ap.add_argument("--timeout", type=int, help=f"초 (기본 장당 {DEFAULT_TIMEOUT_PER_IMAGE})")
    ap.add_argument("--dry-run", action="store_true", help="명령과 지시문만 보여 주고 생성하지 않음")
    args = ap.parse_args(argv)

    if args.check:
        return cmd_check(args)
    try:
        if not args.out:
            raise ToolError("--out이 필요하다.")
        if not 1 <= args.count <= 4:
            raise ToolError("--count는 1~4.")
        summary = run(args)
    except ToolError as e:
        print(f"[오류] {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] in ("ok", "dry_run"):
        return 0
    print("[오류] 그림이 저장되지 않았다. errors·message를 확인한다. 자동으로 다시 만들지 않는다.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
