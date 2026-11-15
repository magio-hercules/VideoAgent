#!/usr/bin/env python3
"""에피소드 기계용 상태 — 읽기·검사·목록.

각 작품의 `생성상태.md` 맨 위 "기계용 상태" 절의 JSON 블록(```json videoagent-state)을 읽는다.
형식과 필드 뜻은 같은 폴더의 README.md가 소유한다. 이 스크립트는 파일을 고치지 않는다.

사용 (작업 폴더 루트에서):
  python _infra/episode-state/episode_state.py show  productions/shorts/EP031_소재
  python _infra/episode-state/episode_state.py check productions/shorts/EP031_소재
  python _infra/episode-state/episode_state.py check productions/shorts/EP031_소재 --handoff
  python _infra/episode-state/episode_state.py list [--json]

종료 코드: 0 = 문제 없음, 1 = 오류 있음, 2 = 사용법·경로 오류.
"""
import argparse
import glob
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
STATE_FILE = "생성상태.md"
SCHEMA = "videoagent.episode-state/1"
BLOCK_RE = re.compile(r"```json[ \t]+videoagent-state[ \t]*\r?\n(.*?)\r?\n```", re.S)

STATUS = ("active", "waiting_operator", "waiting_pc", "handoff_ready", "on_hold", "done")
ASSIGNEE = ("chatgpt", "claude", "operator")
HANDOFF = ("none", "ready", "accepted", "returned")
ACTOR = ("chatgpt", "claude", "operator", "web")
VERSION_KEYS = ("script", "style", "representative", "timeline", "meta", "video")
# 인계(5단계 → 6단계) 때 반드시 정해져 있어야 하는 버전
HANDOFF_VERSIONS = ("script", "style", "representative")
REQUIRED = {
    "schema": str, "episode": str, "topic": str, "stage": int, "status": str, "assignee": str,
    "handoff": dict, "versions": dict, "block_count": (int, type(None)), "next_action": str,
    "pending_operator": list, "updated_at": str, "updated_by": str,
}
REP_RE = re.compile(r"_(B\d{2})[a-z]?_representative\.png$", re.I)


class StateError(Exception):
    pass


def nfc(s):
    return unicodedata.normalize("NFC", s)


def resolve_episode_dir(rel):
    """작업 폴더 기준 상대경로만 받는다. 폴더 또는 생성상태.md 경로."""
    if not rel or os.path.isabs(rel) or re.match(r"^[A-Za-z]:", rel) or "\\" in rel:
        raise StateError(f"작업 폴더 기준 슬래시 상대경로만 허용: '{rel}'")
    if ".." in rel.split("/"):
        raise StateError(f"'..' 경로 거부: '{rel}'")
    p = os.path.realpath(os.path.join(ROOT, rel))
    if os.path.commonpath([p, ROOT]) != ROOT:
        raise StateError(f"작업 폴더 밖 경로 거부: '{rel}'")
    if os.path.isfile(p):
        p = os.path.dirname(p)
    if not os.path.isdir(p):
        raise StateError(f"폴더 없음: '{rel}'")
    return p


def state_path(ep_dir):
    for entry in os.listdir(ep_dir):
        if nfc(entry) == nfc(STATE_FILE):
            return os.path.join(ep_dir, entry)
    raise StateError(f"{STATE_FILE} 없음: {rel_of(ep_dir)}")


def rel_of(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def parse_text(text):
    blocks = BLOCK_RE.findall(text)
    if not blocks:
        raise StateError("기계용 상태 블록(```json videoagent-state) 없음")
    if len(blocks) > 1:
        raise StateError(f"기계용 상태 블록이 {len(blocks)}개 — 하나만 둔다")
    try:
        data = json.loads(blocks[0])
    except json.JSONDecodeError as e:
        raise StateError(f"JSON 파싱 실패: {e.msg} (블록 {e.lineno}행)")
    if not isinstance(data, dict):
        raise StateError("상태 블록 최상위가 객체가 아님")
    return data


def load(ep_dir):
    with open(state_path(ep_dir), encoding="utf-8") as f:
        return parse_text(f.read())


ISO_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2}))?$")
OPTIONAL = {"stage_log"}


def stage_log_errors(log):
    """단계 이력: [{stage, started_at, ended_at, note}] — 시각은 시간대 붙은 ISO, 모르면 날짜만."""
    if not isinstance(log, list):
        return ["stage_log: 배열이어야 한다"]
    errs = []
    for i, x in enumerate(log):
        if not isinstance(x, dict):
            errs.append(f"stage_log[{i}]: 객체여야 한다")
            continue
        st = x.get("stage")
        if not isinstance(st, int) or isinstance(st, bool) or not 0 <= st <= 11:
            errs.append(f"stage_log[{i}].stage: 0~11 정수")
        for k in ("started_at", "ended_at"):
            v = x.get(k)
            if k == "ended_at" and v is None:
                continue
            if not isinstance(v, str) or not ISO_TIME_RE.match(v):
                errs.append(f"stage_log[{i}].{k}: 시간대 붙은 ISO 시각 또는 날짜(YYYY-MM-DD)")
        extra = set(x) - {"stage", "started_at", "ended_at", "note"}
        if extra:
            errs.append(f"stage_log[{i}]: 정의되지 않은 필드 {sorted(extra)}")
    return errs


PENDING_KINDS = ("approve", "choose", "confirm", "cost", "info")
PENDING_KEYS = {"id", "question", "kind", "options", "recommend", "note", "refs"}


def pending_item_errors(x, i):
    """대표 결정 항목: 문자열(간단형) 또는 {question, kind, options …} 객체(결정 카드형)."""
    if isinstance(x, str):
        return [] if x.strip() else [f"pending_operator[{i}]: 빈 문자열"]
    if not isinstance(x, dict):
        return [f"pending_operator[{i}]: 문자열이나 객체여야 한다"]
    errs = []
    if not isinstance(x.get("question"), str) or not x["question"].strip():
        errs.append(f"pending_operator[{i}].question: 필수 문자열")
    if x.get("kind", "info") not in PENDING_KINDS:
        errs.append(f"pending_operator[{i}].kind: {'/'.join(PENDING_KINDS)} 중 하나")
    opts = x.get("options", [])
    if not isinstance(opts, list) or any(not isinstance(o, str) or not o.strip() for o in opts):
        errs.append(f"pending_operator[{i}].options: 문자열 배열")
    elif x.get("kind") == "choose" and len(opts) < 2:
        errs.append(f"pending_operator[{i}]: kind=choose면 options 2개 이상")
    rec = x.get("recommend")
    if rec is not None and (not isinstance(opts, list) or rec not in opts):
        errs.append(f"pending_operator[{i}].recommend: options 중 하나여야 한다")
    if "id" in x and (not isinstance(x["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", x["id"])):
        errs.append(f"pending_operator[{i}].id: 영문·숫자·_- 40자 이하")
    if "refs" in x and (not isinstance(x["refs"], list) or any(not isinstance(r, str) for r in x["refs"])):
        errs.append(f"pending_operator[{i}].refs: 문자열 배열")
    extra = set(x) - PENDING_KEYS
    if extra:
        errs.append(f"pending_operator[{i}]: 정의되지 않은 필드 {sorted(extra)}")
    return errs


def validate(s):
    """형식·값·일관성 오류 목록."""
    errs = []
    for k, t in REQUIRED.items():
        if k not in s:
            errs.append(f"필드 누락: {k}")
        elif not isinstance(s[k], t) or (t is int and isinstance(s[k], bool)):
            errs.append(f"{k}: 형식 오류")
    extra = set(s) - set(REQUIRED) - OPTIONAL
    if extra:
        errs.append(f"정의되지 않은 필드: {sorted(extra)}")
    if "stage_log" in s:
        errs += stage_log_errors(s["stage_log"])
    if errs:
        return errs
    if s["schema"] != SCHEMA:
        errs.append(f"schema는 '{SCHEMA}'")
    if not re.match(r"^EP\d{3,}$", s["episode"]):
        errs.append("episode는 'EP' + 숫자 3자리 이상")
    if not 0 <= s["stage"] <= 11:
        errs.append("stage는 0~11")
    for k, allowed in (("status", STATUS), ("assignee", ASSIGNEE), ("updated_by", ACTOR)):
        if s[k] not in allowed:
            errs.append(f"{k}: '{s[k]}' — 허용 {list(allowed)}")
    h = s["handoff"]
    if set(h) != {"status", "at", "note"}:
        errs.append("handoff 필드는 정확히 status, at, note")
    else:
        if h["status"] not in HANDOFF:
            errs.append(f"handoff.status: '{h['status']}' — 허용 {list(HANDOFF)}")
        if not isinstance(h["at"], (str, type(None))) or not isinstance(h["note"], str):
            errs.append("handoff.at은 문자열 또는 null, handoff.note는 문자열")
    v = s["versions"]
    if set(v) != set(VERSION_KEYS):
        errs.append(f"versions 필드는 정확히 {list(VERSION_KEYS)}")
    elif any(not isinstance(x, (str, type(None))) for x in v.values()):
        errs.append("versions 값은 문자열 또는 null")
    if s["block_count"] is not None and s["block_count"] < 1:
        errs.append("block_count는 1 이상 또는 null")
    for i, x in enumerate(s["pending_operator"]):
        errs += pending_item_errors(x, i)
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})$", s["updated_at"]):
        errs.append("updated_at은 시간대가 붙은 ISO 시각 (예: 2026-11-11T10:00+09:00)")
    if errs:
        return errs
    # 일관성
    st, hs = s["status"], h["status"]
    if st == "handoff_ready" and hs != "ready":
        errs.append("status=handoff_ready면 handoff.status=ready")
    if hs == "ready":
        if st != "handoff_ready":
            errs.append("handoff.status=ready면 status=handoff_ready")
        if s["stage"] != 5:
            errs.append("인계(ready)는 5단계를 마친 상태에서만 (stage=5)")
        if s["assignee"] != "claude":
            errs.append("handoff.status=ready면 assignee=claude")
        if not h["at"]:
            errs.append("handoff.at(인계 시각) 필요")
    if st == "waiting_pc" and s["assignee"] != "claude":
        errs.append("status=waiting_pc면 assignee=claude")
    if st == "waiting_operator" and not s["pending_operator"]:
        errs.append("status=waiting_operator면 pending_operator에 무엇을 기다리는지 적는다")
    if s["stage"] >= 6 and s["assignee"] == "chatgpt":
        errs.append("6단계 이후는 ChatGPT 담당이 아님 (assignee=claude 또는 operator)")
    return errs


def representative_blocks(ep_dir):
    found = set()
    for path in glob.glob(os.path.join(ep_dir, "**", "*.png"), recursive=True):
        m = REP_RE.search(os.path.basename(path))
        if m:
            found.add(m.group(1).upper())
    return found


def handoff_problems(ep_dir, s):
    """5단계 → 6단계 인계 체크리스트 중 파일로 확인할 수 있는 것."""
    probs = []
    for k in HANDOFF_VERSIONS:
        if not s["versions"].get(k):
            probs.append(f"versions.{k} 미정")
    if not s["block_count"]:
        probs.append("block_count 미정")
    brief = [e for e in os.listdir(ep_dir) if nfc(e) == "BRIEF.md"]
    if not brief:
        probs.append("BRIEF.md 없음")
    if s["block_count"]:
        have = representative_blocks(ep_dir)
        need = {f"B{i:02d}" for i in range(1, s["block_count"] + 1)}
        missing = sorted(need - have)
        if missing:
            probs.append(f"대표 그림 없음: {', '.join(missing)} (<EP>_Bxx_representative.png)")
    return probs


def episode_dirs():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "productions", "*", "*", "*"))):
        if nfc(os.path.basename(p)) == nfc(STATE_FILE) and "_template" not in p.replace(os.sep, "/").split("/"):
            out.append(os.path.dirname(p))
    return out


def summary(ep_dir):
    row = {"path": rel_of(ep_dir)}
    try:
        s = load(ep_dir)
    except StateError as e:
        row["error"] = str(e)
        return row
    errs = validate(s)
    if errs:
        row["error"] = "; ".join(errs)
    for k in ("episode", "topic", "stage", "status", "assignee", "next_action", "updated_at"):
        row[k] = s.get(k)
    row["handoff"] = (s.get("handoff") or {}).get("status")
    row["pending_operator"] = s.get("pending_operator")
    return row


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    ap = argparse.ArgumentParser(description="에피소드 기계용 상태 읽기·검사·목록 (파일을 고치지 않음)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "check"):
        sp = sub.add_parser(name)
        sp.add_argument("path", help="작품 폴더(작업 폴더 기준 상대경로)")
        if name == "check":
            sp.add_argument("--handoff", action="store_true", help="5→6단계 인계 체크리스트도 검사")
    lp = sub.add_parser("list")
    lp.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        rows = [summary(d) for d in episode_dirs()]
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            if not rows:
                print("작품 없음 (productions/<종류>/<작품>/생성상태.md)")
            for r in rows:
                if "episode" not in r:
                    print(f"{r['path']}  [오류] {r['error']}")
                    continue
                flag = "  [오류]" if r.get("error") else ""
                print(f"{r['episode']}  {r['stage']}단계  {r['status']:<16} 담당={r['assignee']:<8} "
                      f"인계={r['handoff']:<8} {r['topic']} — {r['next_action']}{flag}")
        return 1 if any(r.get("error") for r in rows) else 0

    try:
        ep = resolve_episode_dir(a.path)
        s = load(ep)
    except StateError as e:
        print(f"[오류] {e}", file=sys.stderr)
        return 2
    if a.cmd == "show":
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    errs = validate(s)
    if not errs and (a.handoff or s["handoff"]["status"] == "ready"):
        errs += [f"인계: {p}" for p in handoff_problems(ep, s)]
    for e in errs:
        print(f"[오류] {e}")
    if not errs:
        print(f"OK — {s['episode']} {s['stage']}단계 {s['status']} (담당 {s['assignee']})")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
