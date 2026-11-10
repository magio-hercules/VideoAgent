#!/usr/bin/env python3
"""공개 저장소 검사 — 커밋·Push 전에 비밀 값·개인 정보·채널 정보가 섞였는지 찾는다.

사용 (작업 폴더 루트에서):
  python _infra/public-check/check_public.py            # Git에 들어갈 모든 파일 검사
  python _infra/public-check/check_public.py --staged   # 스테이징된 파일만 (pre-commit 훅)
  python _infra/public-check/check_public.py --list     # 공개 대상 파일 목록만 출력

검사 대상 목록은 git이 .gitignore를 적용해 정한다. 이 폴더가 아직 Git 저장소가 아니면
임시 Git 디렉터리(작업 폴더 밖)를 만들어 같은 규칙으로 목록을 얻는다. 파일을 고치지 않는다.

찾는 것:
  - 키·토큰 모양 문자열 (sk-, ghp_, hf_, AIza, JWT, Slack, AWS, 개인키 블록 등)
  - 개인 절대경로 (드라이브 문자 경로, /Users/, /home/)
  - 이메일 주소
  - private/denylist.txt의 문자열과 .env의 값 (채널명·핸들·보이스 ID 등)
  - 있어서는 안 되는 파일 (private/ — 안내문 README.md 제외, .env, 미디어·모델·압축 파일, 2MB 초과)
한 줄에 'public-check: allow'가 있으면 그 줄의 경로·이메일 규칙은 건너뛴다(키·금지 문자열은 건너뛰지 않음).
찾은 값은 출력하지 않고 위치와 규칙 이름만 보여 준다. 문제가 있으면 종료 코드 1.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MAX_BYTES = 2 * 1024 * 1024
BLOCKED_PREFIXES = ("private/", ".env", ".idea/", "_scratch/")
ALLOWED_EXCEPTIONS = {".env.example", "private/README.md"}  # 공개용 양식·안내문
BLOCKED_EXT = {".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a", ".flac", ".png", ".jpg", ".jpeg",
               ".webp", ".gif", ".psd", ".tgz", ".tar", ".gz", ".zip", ".bin", ".safetensors",
               ".ckpt", ".ttf", ".otf", ".pyc", ".srt"}
ALLOW_MARK = "public-check: allow"

KEY_RULES = [
    ("openai/anthropic 키", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("GitHub 토큰", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}")),
    ("Hugging Face 토큰", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("Google API 키", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("AWS 키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack 토큰", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{20,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}")),
    ("개인키 블록", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("키 대입", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+]{16,}")),
]
SOFT_RULES = [
    ("절대경로(드라이브)", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]{1,2}[\w .$~-]{2,}[\\/]")),
    ("절대경로(홈)", re.compile(r"(?:/Users/|/home/)[A-Za-z0-9._-]+")),
    ("이메일", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[A-Za-z]{2,}\b")),
]
EMAIL_OK = {"noreply@anthropic.com", "noreply@github.com"}


def git(args, env=None):
    return subprocess.run(["git"] + args, cwd=ROOT, capture_output=True, text=True, env=env,
                          encoding="utf-8", errors="replace")


def public_files(staged):
    if os.path.isdir(os.path.join(ROOT, ".git")):
        if staged:
            r = git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"])
        else:
            r = git(["ls-files", "-co", "--exclude-standard", "-z"])
        if r.returncode != 0:
            sys.exit(f"git 오류: {r.stderr.strip()}")
        return sorted(p for p in r.stdout.split("\0") if p)
    tmp = tempfile.mkdtemp(prefix="pubcheck-")
    try:
        env = dict(os.environ, GIT_DIR=os.path.join(tmp, "git"), GIT_WORK_TREE=ROOT)
        r = git(["init", "-q"], env=env)
        if r.returncode != 0:
            sys.exit(f"git init 오류: {r.stderr.strip()}")
        r = git(["ls-files", "-o", "--exclude-standard", "-z"], env=env)
        if r.returncode != 0:
            sys.exit(f"git 오류: {r.stderr.strip()}")
        return sorted(p for p in r.stdout.split("\0") if p)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def load_terms():
    terms = []
    path = os.path.join(ROOT, "private", "denylist.txt")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                t = line.strip()
                if t and not t.startswith("#"):
                    terms.append(("금지 문자열(denylist)", t))
    env_path = os.path.join(ROOT, ".env")
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                val = val.strip().strip("'\"")
                if len(val) >= 6:
                    terms.append((f".env 값({key.strip()})", val))
    return terms


def scan(files):
    problems = []
    terms = load_terms()
    lowered = [(name, t.lower()) for name, t in terms]
    for rel in files:
        low = rel.lower()
        if low.startswith(BLOCKED_PREFIXES) and rel not in ALLOWED_EXCEPTIONS:
            problems.append((rel, 0, "공개하면 안 되는 경로"))
            continue
        if os.path.splitext(low)[1] in BLOCKED_EXT:
            problems.append((rel, 0, "미디어·모델·압축·폰트 파일"))
            continue
        full = os.path.join(ROOT, *rel.split("/"))
        if not os.path.isfile(full):
            continue
        size = os.path.getsize(full)
        if size > MAX_BYTES:
            problems.append((rel, 0, f"큰 파일({size // 1024}KB > {MAX_BYTES // 1024}KB)"))
            continue
        with open(full, "rb") as f:
            raw = f.read()
        if b"\0" in raw[:8192]:
            problems.append((rel, 0, "바이너리 파일"))
            continue
        text = raw.decode("utf-8", errors="replace")
        for no, line in enumerate(text.splitlines(), 1):
            for name, rx in KEY_RULES:
                if rx.search(line):
                    problems.append((rel, no, name))
            line_low = line.lower()
            for name, t in lowered:
                if t in line_low:
                    problems.append((rel, no, name))
            if ALLOW_MARK in line:
                continue
            for name, rx in SOFT_RULES:
                for m in rx.finditer(line):
                    if name == "이메일" and m.group(0).lower() in EMAIL_OK:
                        continue
                    problems.append((rel, no, name))
                    break
    return problems, len(terms)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    ap = argparse.ArgumentParser(description="공개 저장소 검사")
    ap.add_argument("--staged", action="store_true", help="스테이징된 파일만 검사")
    ap.add_argument("--list", action="store_true", help="공개 대상 파일 목록만 출력")
    a = ap.parse_args()
    files = public_files(a.staged)
    if a.list:
        for p in files:
            print(p)
        print(f"공개 대상 {len(files)}개")
        return 0
    problems, nterms = scan(files)
    if not os.path.isfile(os.path.join(ROOT, "private", "denylist.txt")):
        print("WARN private/denylist.txt 없음 — 채널·개인 식별 문자열 검사를 건너뜀")
    for rel, no, rule in problems:
        print(f"FAIL {rel}{':' + str(no) if no else ''}  {rule}")
    print(f"검사 파일 {len(files)}개, 금지 문자열 {nterms}개 — "
          + ("통과" if not problems else f"문제 {len(problems)}건 (값은 출력하지 않음)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
