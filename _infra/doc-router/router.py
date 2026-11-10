#!/usr/bin/env python3
"""VideoAgent 문서 라우터 — 읽기 전용 선택기.

현재 요청에 필요한 문서만 골라 경로·존재 여부·바이트를 보여준다.
네트워크, 패키지 설치, shell/subprocess, eval/exec, 자격 증명 접근,
파일 쓰기를 하지 않는다. 표준 라이브러리만 사용한다.

사용:
  python _infra/doc-router/router.py --tags "프롬프트" --path "productions/shorts/작품"
  python _infra/doc-router/router.py --tags "재개" --path "productions/shorts/작품" --json
  python _infra/doc-router/router.py --check
"""
import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ROUTES_PATH = "docs/agent/routes.json"
SCHEMA_PATH = "docs/agent/routes.schema.json"
SYSTEM_PATH = ".agent-system.json"
BASE_ROUTE_IDS = [
    "repo-docs", "story-planning", "prompt-writing", "local-run",
    "paid-generation", "resume-project", "review-delivery",
]
SKIP_WALK_DIRS = {".git", "node_modules", "__pycache__"}

ROUTE_KEYS = {"id", "description", "match", "read_order", "conditional_docs"}
MATCH_KEYS = {"tags", "path_globs"}
COND_KEYS = {"description", "when", "read_order", "nearest"}
TOP_KEYS = {"schema_version", "limits", "forbidden_default", "representative_tags", "routes"}
LIMIT_KEYS = {"root_agent_max_bytes", "initial_route_max_bytes", "initial_route_warning_ratio"}
TAG_RE = re.compile(r"^[^\s,]{1,40}$")
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


class RouterError(Exception):
    pass


def nfc(s):
    return unicodedata.normalize("NFC", s)


# ---------- 경로 안전 ----------

def relpath_problem(p):
    """작업 폴더 기준 슬래시 상대경로인지 검사. 문제가 있으면 이유 문자열."""
    if not isinstance(p, str) or not p:
        return "빈 경로"
    if "\\" in p:
        return "역슬래시 금지 (슬래시 상대경로만)"
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return "절대경로 금지"
    if any(part == ".." for part in p.split("/")):
        return "'..' 금지"
    return None


def inside_root(abs_path):
    real = os.path.realpath(abs_path)
    try:
        return os.path.commonpath([real, ROOT]) == ROOT
    except ValueError:  # 다른 드라이브
        return False


def safe_abs(rel):
    prob = relpath_problem(rel)
    if prob:
        raise RouterError(f"경로 거부 '{rel}': {prob}")
    abs_path = os.path.join(ROOT, *rel.split("/"))
    # 아직 없는 경로는 존재하는 가장 가까운 상위로 판단
    probe = abs_path
    while not os.path.exists(probe) and os.path.dirname(probe) != probe:
        probe = os.path.dirname(probe)
    if not inside_root(probe) or not inside_root(abs_path):
        raise RouterError(f"경로 거부 '{rel}': 작업 폴더 밖으로 향함 (링크·junction 포함)")
    return abs_path


# ---------- glob ----------

def glob_to_re(glob):
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif glob.startswith("**", i):
            out.append(".*"); i += 2
        elif glob[i] == "*":
            out.append("[^/]*"); i += 1
        elif glob[i] == "?":
            out.append("[^/]"); i += 1
        else:
            out.append(re.escape(glob[i])); i += 1
    return re.compile("^" + "".join(out) + "$")


def glob_match(globs, rel):
    rel = nfc(rel.strip("/"))
    return any(glob_to_re(nfc(g)).match(rel) for g in globs)


# ---------- 로드 ----------

def load_json(rel):
    abs_path = safe_abs(rel)
    with open(abs_path, "r", encoding="utf-8") as f:
        return json.load(f)


def file_bytes(rel):
    abs_path = safe_abs(rel)
    return os.path.getsize(abs_path) if os.path.isfile(abs_path) else None


# ---------- 구조 검사 ----------

def structure_errors(cfg):
    errs = []
    if not isinstance(cfg, dict):
        return ["routes.json 최상위가 객체가 아님"]
    keys = set(cfg)
    if keys - TOP_KEYS:
        errs.append(f"정의되지 않은 최상위 필드: {sorted(keys - TOP_KEYS)}")
    if TOP_KEYS - keys:
        errs.append(f"누락된 최상위 필드: {sorted(TOP_KEYS - keys)}")
        return errs
    if cfg["schema_version"] != 1:
        errs.append("schema_version은 1이어야 함")
    lim = cfg["limits"]
    if not isinstance(lim, dict) or set(lim) != LIMIT_KEYS:
        errs.append(f"limits 필드는 정확히 {sorted(LIMIT_KEYS)}")
    else:
        if not (isinstance(lim["root_agent_max_bytes"], int) and 0 < lim["root_agent_max_bytes"] <= 12288):
            errs.append("root_agent_max_bytes는 1..12288 정수 (완화는 사용자 승인 필요)")
        if not (isinstance(lim["initial_route_max_bytes"], int) and lim["initial_route_max_bytes"] > 0):
            errs.append("initial_route_max_bytes는 양의 정수")
        r = lim["initial_route_warning_ratio"]
        if not (isinstance(r, (int, float)) and 0 < r <= 1):
            errs.append("initial_route_warning_ratio는 (0,1]")
    fd = cfg["forbidden_default"]
    if not isinstance(fd, list) or not fd:
        errs.append("forbidden_default는 비어 있지 않은 배열")
    else:
        for p in fd:
            prob = relpath_problem(p)
            if prob:
                errs.append(f"forbidden_default '{p}': {prob}")
        if len(set(fd)) != len(fd):
            errs.append("forbidden_default 중복")
        for must in ("CONTEXT.md", "renders.md"):
            if must not in fd:
                errs.append(f"forbidden_default에 '{must}' 필요")
        if not any("logs" in p for p in fd):
            errs.append("forbidden_default에 logs 패턴 필요")

    def check_match(m, where):
        if not isinstance(m, dict):
            errs.append(f"{where}: 객체가 아님"); return
        if set(m) - MATCH_KEYS:
            errs.append(f"{where}: 정의되지 않은 필드 {sorted(set(m) - MATCH_KEYS)}")
        if not (m.get("tags") or m.get("path_globs")):
            errs.append(f"{where}: tags 또는 path_globs 중 하나 이상 필요")
        for t in m.get("tags", []):
            if not isinstance(t, str) or not TAG_RE.match(t):
                errs.append(f"{where}: 태그 형식 오류 '{t}'")
        if len(set(m.get("tags", []))) != len(m.get("tags", [])):
            errs.append(f"{where}: 태그 중복")
        for g in m.get("path_globs", []):
            prob = relpath_problem(g)
            if prob:
                errs.append(f"{where}: path_glob '{g}': {prob}")

    def check_paths(lst, where):
        if not isinstance(lst, list):
            errs.append(f"{where}: 배열이 아님"); return
        if len(set(lst)) != len(lst):
            errs.append(f"{where}: 경로 중복")
        for p in lst:
            prob = relpath_problem(p)
            if prob:
                errs.append(f"{where}: '{p}': {prob}")

    routes = cfg["routes"]
    ids = []
    if not isinstance(routes, list) or not routes:
        errs.append("routes는 비어 있지 않은 배열")
        routes = []
    for i, r in enumerate(routes):
        w = f"routes[{i}]"
        if not isinstance(r, dict):
            errs.append(f"{w}: 객체가 아님"); continue
        if set(r) - ROUTE_KEYS:
            errs.append(f"{w}: 정의되지 않은 필드 {sorted(set(r) - ROUTE_KEYS)}")
        if ROUTE_KEYS - set(r):
            errs.append(f"{w}: 누락 필드 {sorted(ROUTE_KEYS - set(r))}"); continue
        if not ID_RE.match(str(r["id"])):
            errs.append(f"{w}: id 형식 오류")
        ids.append(r["id"])
        w = f"route '{r['id']}'"
        if not r["description"]:
            errs.append(f"{w}: description 비어 있음")
        check_match(r["match"], f"{w}.match")
        check_paths(r["read_order"], f"{w}.read_order")
        for j, c in enumerate(r["conditional_docs"]):
            cw = f"{w}.conditional_docs[{j}]"
            if not isinstance(c, dict):
                errs.append(f"{cw}: 객체가 아님"); continue
            if set(c) - COND_KEYS:
                errs.append(f"{cw}: 정의되지 않은 필드 {sorted(set(c) - COND_KEYS)}")
            if not c.get("description") or "when" not in c:
                errs.append(f"{cw}: description과 when 필요")
            if "when" in c:
                check_match(c["when"], f"{cw}.when")
            if not (c.get("read_order") or c.get("nearest")):
                errs.append(f"{cw}: read_order 또는 nearest 필요")
            if "read_order" in c:
                check_paths(c["read_order"], f"{cw}.read_order")
            for n in c.get("nearest", []):
                if not isinstance(n, str) or "/" in n or "\\" in n or not n.endswith(".md"):
                    errs.append(f"{cw}.nearest: 파일명만 허용 '{n}'")
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errs.append(f"route ID 중복: {dup}")

    rt = cfg["representative_tags"]
    if not isinstance(rt, dict) or not rt:
        errs.append("representative_tags는 비어 있지 않은 객체")
    else:
        linked = set()
        for tag, rids in rt.items():
            if not TAG_RE.match(tag):
                errs.append(f"representative_tags: 태그 형식 오류 '{tag}'")
            if not isinstance(rids, list) or not rids or len(set(rids)) != len(rids):
                errs.append(f"representative_tags['{tag}']: 중복 없는 비어 있지 않은 배열 필요"); continue
            for rid in rids:
                if rid not in ids:
                    errs.append(f"representative_tags['{tag}']: 없는 route '{rid}'")
                linked.add(rid)
        for rid in BASE_ROUTE_IDS:
            if rid not in ids:
                errs.append(f"기본 라우트 누락: {rid}")
            if rid not in linked:
                errs.append(f"대표 태그에 연결되지 않은 기본 라우트: {rid}")
    return errs


def is_forbidden(cfg, rel):
    return glob_match(cfg.get("forbidden_default", []), rel)


# ---------- 선택 ----------

def split_tags(s):
    return [t for t in re.split(r"[,\s]+", s or "") if t]


def modifier_tags(cfg):
    """조건부 문서의 when.tags — 라우트를 고르지는 않고 문서만 추가하는 태그."""
    out = set()
    for r in cfg["routes"]:
        for c in r["conditional_docs"]:
            out.update(c["when"].get("tags", []))
    return out


def resolve_route_ids(cfg, tags, path):
    rep = cfg["representative_tags"]
    ids = [r["id"] for r in cfg["routes"]]
    mods = modifier_tags(cfg)
    chosen, unknown = [], []
    for t in tags:
        hit = []
        if t in rep:
            hit = rep[t]
        elif t.lower() in rep:
            hit = rep[t.lower()]
        elif t in ids:
            hit = [t]
        for r in cfg["routes"]:
            if t in r["match"].get("tags", []) and r["id"] not in hit:
                hit = hit + [r["id"]]
        if not hit and t not in mods:
            unknown.append(t)
        for h in hit:
            if h not in chosen:
                chosen.append(h)
    if path:
        for r in cfg["routes"]:
            if r["match"].get("path_globs") and glob_match(r["match"]["path_globs"], path):
                if r["id"] not in chosen:
                    chosen.append(r["id"])
    return chosen, unknown


def when_ok(when, tags, path):
    ok_tags = bool(set(when.get("tags", [])) & set(tags)) if when.get("tags") else False
    ok_path = bool(path) and glob_match(when.get("path_globs", []), path) if when.get("path_globs") else False
    return ok_tags or ok_path


def find_nearest(cfg, name, path):
    """대상 경로에서 위로 올라가며 가장 가까운 name 파일. 작업 폴더 루트 자체는 제외."""
    abs_path = safe_abs(path)
    cur = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
    while True:
        if not inside_root(cur):
            return None
        if os.path.realpath(cur) == ROOT:
            return None  # 루트의 CONTEXT/renders 등은 기본으로 읽지 않음
        if os.path.isdir(cur):
            for entry in sorted(os.listdir(cur)):
                if nfc(entry) == nfc(name) and os.path.isfile(os.path.join(cur, entry)):
                    rel = os.path.relpath(os.path.join(cur, entry), ROOT).replace(os.sep, "/")
                    if is_forbidden(cfg, rel):
                        return None
                    safe_abs(rel)
                    return rel
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def select(cfg, tags, path):
    if path:
        prob = relpath_problem(path)
        if prob:
            raise RouterError(f"--path 거부 '{path}': {prob}")
        path = path.strip("/")
        safe_abs(path)
    route_ids, unknown = resolve_route_ids(cfg, tags, path)
    docs, seen, notes = [], set(), []

    def add(rel, reason):
        key = nfc(rel)
        if key in seen:
            return
        if is_forbidden(cfg, rel):
            notes.append(f"기본 금지 문서 제외: {rel}")
            return
        seen.add(key)
        size = file_bytes(rel)
        docs.append({"path": rel, "reason": reason, "exists": size is not None, "bytes": size or 0})

    by_id = {r["id"]: r for r in cfg["routes"]}
    for rid in route_ids:
        r = by_id[rid]
        for rel in r["read_order"]:
            add(rel, f"{rid}: 기본")
        for c in r["conditional_docs"]:
            if not when_ok(c["when"], tags, path):
                continue
            for rel in c.get("read_order", []):
                add(rel, f"{rid}: 조건부 — {c['description']}")
            if c.get("nearest"):
                if not path:
                    notes.append(f"{rid}: 가까운 {', '.join(c['nearest'])}를 찾으려면 --path로 작품 경로를 지정")
                    continue
                for name in c["nearest"]:
                    found = find_nearest(cfg, name, path)
                    if found:
                        add(found, f"{rid}: 가까운 {name}")
                    else:
                        notes.append(f"{rid}: '{path}' 근처에 {name} 없음")
        if rid == "resume-project" and not path:
            notes.append("resume-project: 이어갈 작품 경로(--path productions/...)를 사용자에게 확인")
    total = sum(d["bytes"] for d in docs)
    lim = cfg["limits"]
    status = "ok"
    if total > lim["initial_route_max_bytes"]:
        status = "over_limit"
    elif total > lim["initial_route_max_bytes"] * lim["initial_route_warning_ratio"]:
        status = "warning"
    return {
        "tags": tags, "path": path, "routes": route_ids, "unknown_tags": unknown,
        "docs": docs, "total_bytes": total, "limit_bytes": lim["initial_route_max_bytes"],
        "status": status if route_ids else "no_route", "notes": notes,
    }


# ---------- --check ----------

def run_check(cfg):
    errs, warns, info = [], [], []
    errs += structure_errors(cfg)
    try:
        load_json(SCHEMA_PATH)
        info.append(f"{SCHEMA_PATH}: JSON 파싱 OK")
    except Exception as e:  # noqa
        errs.append(f"{SCHEMA_PATH}: {e}")
    if errs:
        return errs, warns, info
    lim = cfg["limits"]
    agents = file_bytes("AGENTS.md")
    if agents is None:
        errs.append("AGENTS.md 없음")
    else:
        with open(safe_abs("AGENTS.md"), "rb") as f:
            try:
                f.read().decode("utf-8")
            except UnicodeDecodeError:
                errs.append("AGENTS.md가 UTF-8이 아님")
        if agents > lim["root_agent_max_bytes"]:
            errs.append(f"AGENTS.md {agents}B > {lim['root_agent_max_bytes']}B")
        else:
            info.append(f"AGENTS.md {agents}B ≤ {lim['root_agent_max_bytes']}B")
    static = []
    for r in cfg["routes"]:
        static += [(r["id"], p, "기본") for p in r["read_order"]]
        for c in r["conditional_docs"]:
            static += [(r["id"], p, "조건부") for p in c.get("read_order", [])]
    for rid, p, kind in static:
        try:
            if file_bytes(p) is None:
                errs.append(f"{rid} {kind} 문서 없음: {p}")
        except RouterError as e:
            errs.append(str(e))
        if is_forbidden(cfg, p):
            errs.append(f"{rid} {kind} 문서가 기본 금지 대상: {p}")
    info.append(f"정적 라우트 문서 {len(static)}개 검사")
    # 루트 밖으로 향하는 symlink·junction
    for dirpath, dirnames, filenames in os.walk(ROOT, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_WALK_DIRS]
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            if (os.path.islink(full) or (hasattr(os.path, "isjunction") and os.path.isjunction(full))) \
                    and not inside_root(full):
                errs.append(f"작업 폴더 밖을 가리키는 링크: {os.path.relpath(full, ROOT)}")
    # 시스템 표식
    if os.path.isfile(safe_abs(SYSTEM_PATH)):
        try:
            sysj = load_json(SYSTEM_PATH)
            info.append(f"{SYSTEM_PATH}: guide_version {sysj.get('guide_version')}")
            for m in sysj.get("managed_files", []):
                p = m.get("path", "")
                prob = relpath_problem(p)
                if prob:
                    errs.append(f"{SYSTEM_PATH} managed '{p}': {prob}"); continue
                ap = safe_abs(p)
                if not os.path.isfile(ap):
                    warns.append(f"관리 파일 없음: {p}"); continue
                with open(ap, "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()
                if h != m.get("baseline_sha256"):
                    warns.append(f"기준 해시와 다름(사용자 수정 가능): {p}")
        except Exception as e:  # noqa
            errs.append(f"{SYSTEM_PATH}: {e}")
    else:
        warns.append(f"{SYSTEM_PATH} 없음")
    return errs, warns, info


# ---------- 출력 ----------

def print_selection(res):
    print(f"태그: {', '.join(res['tags']) or '(없음)'}  경로: {res['path'] or '(없음)'}")
    if res["unknown_tags"]:
        print(f"알 수 없는 태그: {', '.join(res['unknown_tags'])}")
    if not res["routes"]:
        print("맞는 라우트 없음 — 모든 Markdown을 읽지 말고 사용자에게 의도를 좁혀 물을 것.")
        return
    print(f"라우트: {' → '.join(res['routes'])}")
    print("읽을 문서 (순서대로):")
    for i, d in enumerate(res["docs"], 1):
        ex = f"{d['bytes']}B" if d["exists"] else "없음"
        print(f"  {i}. {d['path']}  [{ex}]  — {d['reason']}")
    print(f"합계: {res['total_bytes']}B / 한도 {res['limit_bytes']}B  상태: {res['status']}")
    for n in res["notes"]:
        print(f"  참고: {n}")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    ap = argparse.ArgumentParser(description="VideoAgent 읽기 전용 문서 라우터")
    ap.add_argument("--tags", default="", help="작업 태그 (쉼표·공백 구분)")
    ap.add_argument("--path", default="", help="작업 폴더 기준 대상 경로")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    ap.add_argument("--check", action="store_true", help="구조 검사")
    a = ap.parse_args(argv)
    try:
        cfg = load_json(ROUTES_PATH)
        if a.check:
            errs, warns, info = run_check(cfg)
            if a.json:
                print(json.dumps({"ok": not errs, "errors": errs, "warnings": warns, "info": info},
                                 ensure_ascii=False, indent=2))
            else:
                for x in info:
                    print(f"OK   {x}")
                for x in warns:
                    print(f"WARN {x}")
                for x in errs:
                    print(f"FAIL {x}")
                print("검사 결과:", "통과" if not errs else f"실패 {len(errs)}건")
            return 0 if not errs else 1
        se = structure_errors(cfg)
        if se:
            raise RouterError("routes.json 구조 오류: " + "; ".join(se))
        res = select(cfg, split_tags(a.tags), a.path)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print_selection(res)
        if res["status"] == "no_route":
            return 2
        return 1 if res["status"] == "over_limit" else 0
    except RouterError as e:
        if a.json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"오류: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
