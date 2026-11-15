#!/usr/bin/env python3
"""제작 보드(claude.ai 아티팩트)의 `episodes` 컬렉션에 올릴 문서와 쓰기 묶음(batch)을 만든다.

입력: 작품 폴더 상태 블록(_infra/episode-state) + 회차 목록 사본(private/episode-index.md, 있으면).
출력(파일만 쓰고 보드에는 쓰지 않는다 — 쓰기는 에이전트가 ArtifactData 도구로 한다):
  <out>/episodes/<doc_id>.json   문서마다 하나
  <out>/outputs/<EP>-s<절>.json   편별 BRIEF.md 결과물(단계별 절) — 견본 그대로인 칸은 뺀다
  <out>/media_upload.json         새로 생기거나 바뀐 단계별 그림(04_화면설계·05_제작/대표이미지·07_게시준비) — 에이전트가 보드에 올린다
  <out>/meta/sync.json, <out>/log/<id>.json
  <out>/batch.json               지난 커밋 이후 바뀐 문서만 담은 쓰기 목록 (+ meta/sync, log)
  <out>/manifest.json            요약

명령:
  build  [--all]   문서를 만들고 바뀐 것만 batch.json에 담는다 (--all: 전부)
  media-batch --map <대응표.json>   그림을 올린 뒤, 자산 id로 media 문서 쓰기 묶음(media_batch.json)을 만든다
  commit           보드에 쓴 뒤 실행. 이번 build의 내용 지문을 기준으로 저장해 다음 build가 비교한다

출력 폴더는 저장소 밖이나 _scratch/ 아래만 허용한다(회차 목록은 채널 정보라 Git에 남기지 않는다).
표준 라이브러리만 쓴다. 종료 코드: 0 성공, 2 사용법 오류.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "episode-state"))
import episode_state as es  # noqa: E402

ROOT = es.ROOT
DEFAULT_INDEX = os.path.join("private", "episode-index.md")
EP_RE = re.compile(r"EP(\d{3,})")
RANGE_RE = re.compile(r"EP(\d{3,})(?:\s*~\s*(?:EP)?(\d{3,}))?")
UNKNOWN = ("미확인", "", "—", "-")
CACHE = "commit_hashes.json"
OUT_PREFIX = "outputs/"
LAST = "last_build_hashes.json"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="minutes")


def clean(cell: str) -> str:
    return re.sub(r"\*\*|`", "", cell).strip()


def content_hash(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k != "content_hash"}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------- 회차 목록 ----------

def parse_index(text: str) -> list[dict]:
    """회차 목록 표(| 회차 | 소재 | 작업 코드 | 납품물 | 상태 | 공개 |)를 읽는다."""
    rows, header = [], None
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [clean(c) for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) < 6:
            continue
        ep, topic, code, delivered, status, published = cells[:6]
        if topic.startswith("(다음 편)"):
            continue
        rows.append({"label": ep, "topic": topic, "work_code": code, "delivered": delivered,
                     "index_status": status, "published": published})
    return rows


def index_doc(row: dict, pilot_no: int) -> tuple[str, dict]:
    m = RANGE_RE.search(row["label"])
    if m:
        doc_id = "EP" + m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
        order = int(m.group(1))
    else:
        doc_id = f"PILOT{pilot_no}"
        order = -pilot_no
    st = row["index_status"]
    if "납품" in st:
        status, stage = "delivered", 9
    elif "검수" in st:
        status, stage = "delivered", 8
    else:
        status, stage = "unknown", None
    topic = row["topic"]
    doc = {
        "episode": row["label"], "topic": None if topic in UNKNOWN else topic, "source": "index",
        "order": order, "stage": stage, "status": status, "assignee": None,
        "work_code": None if row["work_code"] in UNKNOWN else row["work_code"],
        "delivered": None if row["delivered"] in UNKNOWN else row["delivered"],
        "index_status": st,
        "published": None if row["published"] in UNKNOWN else row["published"],
    }
    return doc_id, doc


# ---------- 상태 블록 ----------

def normalize_pending(items) -> list[dict]:
    """대표 결정 항목을 보드용 객체로 맞춘다. 문자열은 kind=info 카드가 된다. id는 없으면 질문 글로 만든다."""
    out = []
    for x in items or []:
        if isinstance(x, str):
            x = {"question": x}
        if not isinstance(x, dict) or not isinstance(x.get("question"), str):
            continue
        q = x["question"].strip()
        pid = x.get("id") or "p" + hashlib.sha1(q.encode("utf-8")).hexdigest()[:8]
        out.append({"id": pid, "question": q, "kind": x.get("kind", "info"),
                    "options": list(x.get("options") or []), "recommend": x.get("recommend"),
                    "note": x.get("note"), "refs": list(x.get("refs") or [])})
    return out


def state_doc(ep_dir: str) -> tuple[str | None, dict]:
    rel = es.rel_of(ep_dir)
    try:
        s = es.load(ep_dir)
    except es.StateError as e:
        return None, {"path": rel, "error": str(e)}
    errs = es.validate(s)
    ep = s.get("episode") or ""
    m = EP_RE.search(ep)
    doc = {
        "episode": ep, "topic": s.get("topic"), "source": "state",
        "order": int(m.group(1)) if m else 0,
        "stage": s.get("stage"), "status": s.get("status"), "assignee": s.get("assignee"),
        "next_action": s.get("next_action"), "pending_operator": normalize_pending(s.get("pending_operator")),
        "handoff": s.get("handoff") or {"status": "none"}, "versions": s.get("versions") or {},
        "block_count": s.get("block_count"), "updated_at": s.get("updated_at"),
        "updated_by": s.get("updated_by"), "path": rel, "stage_log": s.get("stage_log") or [],
    }
    if errs:
        doc["state_errors"] = errs
    return (ep if m else None), doc


# ---------- 단계별 결과물 (BRIEF.md) ----------

BRIEF_FILE = "BRIEF.md"
TEMPLATE_BRIEF = os.path.join(ROOT, "productions", "_template", BRIEF_FILE)
SEC_RE = re.compile(r"^##\s+(\d+)\.\s*(.+?)\s*$")
STAGE_RE = re.compile(r"\((\d+)(?:\s*~\s*(\d+))?단계\)")
OUT_MAX_CHARS = 200_000  # 문서 하나가 DB 한도에 닿지 않게


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _cells(line: str) -> list[str]:
    return [clean(c) for c in line.strip().strip("|").split("|")]


def brief_blocks(lines: list[str]) -> list[dict]:
    """절 본문을 블록으로 나눈다: text(문단), pre(코드 블록), table(표), h(소제목)."""
    blocks, i, para = [], 0, []

    def flush():
        if para:
            blocks.append({"type": "text", "text": clean("\n".join(para))})
            para.clear()

    while i < len(lines):
        line = lines[i]
        st = line.strip()
        if st.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            blocks.append({"type": "pre", "text": "\n".join(lines[i + 1:j]).rstrip()})
            i = j + 1
            continue
        if st.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            head = _cells(rows[0])
            body = [r for r in rows[1:] if not all(set(c) <= set("-: ") for c in _cells(r))]
            blocks.append({"type": "table", "head": head, "rows": [_cells(r) for r in body], "raw": body})
            continue
        if st.startswith("#"):
            flush()
            blocks.append({"type": "h", "text": clean(st.lstrip("#"))})
        elif st in ("", "---"):
            flush()
        else:
            para.append(st)
        i += 1
    flush()
    return blocks


def template_keys(text: str | None) -> set[str]:
    """견본 BRIEF에 그대로 있는 문단·코드 블록·표 행(= 아직 안 채운 칸)을 알아보는 열쇠."""
    keys = set()
    if not text:
        return keys
    for b in brief_blocks(text.splitlines()):
        if b["type"] == "table":
            keys.update(_norm(r) for r in b["raw"])
        elif b["type"] in ("text", "pre", "h"):
            keys.add(_norm(b["text"]))
    return keys


def parse_brief(text: str, tmpl: set[str]) -> list[dict]:
    """BRIEF.md를 절(## N. 제목) 단위 결과물로 나눈다. 견본 그대로인 부분은 빼고, 내용이 남은 절만 돌려준다."""
    secs, cur = [], None
    for line in text.splitlines():
        m = SEC_RE.match(line)
        if m:
            cur = {"section": m.group(1), "title": m.group(2), "lines": []}
            secs.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    out = []
    for s in secs:
        blocks = []
        for b in brief_blocks(s["lines"]):
            if b["type"] == "table":
                keep = [c for c, r in zip(b["rows"], b["raw"]) if _norm(r) not in tmpl]
                if keep:
                    blocks.append({"type": "table", "head": b["head"], "rows": keep})
            elif _norm(b["text"]) not in tmpl and b["text"]:
                blocks.append(b)
        if not any(b["type"] != "h" for b in blocks):
            continue
        sm = STAGE_RE.search(s["title"])
        stages = list(range(int(sm.group(1)), int(sm.group(2) or sm.group(1)) + 1)) if sm else []
        title = STAGE_RE.sub("", s["title"]).strip()
        out.append({"section": s["section"], "title": title, "stages": stages, "blocks": blocks})
    return out


def output_docs(ep_dir: str, ep: str, tmpl: set[str]) -> dict:
    path = os.path.join(ep_dir, BRIEF_FILE)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        secs = parse_brief(f.read(), tmpl)
    docs = {}
    for s in secs:
        doc = {"episode": ep, "source": BRIEF_FILE, "path": es.rel_of(path), **s}
        raw = json.dumps(doc, ensure_ascii=False)
        if len(raw) > OUT_MAX_CHARS:
            doc["blocks"] = [{"type": "text", "text": f"내용이 길어 보드에는 싣지 못했습니다. {doc['path']} §{s['section']}를 보세요."}]
            doc["truncated"] = True
        doc["content_hash"] = content_hash(doc)
        docs[f"{ep}-s{s['section']}"] = doc
    return docs


# ---------- 그림 결과물 ----------

MEDIA_DIRS = (("04_화면설계", 4), ("05_제작/대표이미지", 5), ("05_제작/클립", 6), ("07_게시준비", 9))  # 폴더 → 단계
MEDIA_EXT = (".png", ".jpg", ".jpeg", ".webp", ".mp4")
MEDIA_PREFIX = "media/"
MEDIA_UPLOAD = "media_upload.json"


def media_caption(rel: str, ep: str) -> str:
    stem = os.path.splitext(os.path.basename(rel))[0]
    if stem.startswith(ep + "_"):
        stem = stem[len(ep) + 1:]
    return stem.replace("_", " ")


def media_files(ep_dir: str, ep: str) -> dict:
    """편 폴더의 단계별 그림을 찾는다. 키는 보드 문서 id(<EP>-m<경로 지문>), 값에 파일 지문(sha)을 담는다."""
    out = {}
    for sub, stage in MEDIA_DIRS:
        base = os.path.join(ep_dir, *sub.split("/"))
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if not x.startswith("_")]  # _rejected·_superseded 같은 버린 판은 올리지 않는다
            for fn in sorted(files):
                if not fn.lower().endswith(MEDIA_EXT):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, ep_dir).replace(os.sep, "/")
                with open(full, "rb") as f:
                    sha = hashlib.sha256(f.read()).hexdigest()[:16]
                doc_id = f"{ep}-m" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:10]
                out[doc_id] = {"episode": ep, "stage": stage, "rel": rel, "path": es.rel_of(full),
                               "file": full, "caption": media_caption(rel, ep), "sha": sha}
    return out


def build_media(ep_dirs: list[str]) -> dict:
    media = {}
    for d in ep_dirs:
        doc_id, doc = state_doc(d)
        stage = doc.get("stage") if isinstance(doc.get("stage"), int) else 0
        if doc_id and doc.get("status") != "done" and stage <= 9:  # 공개 전 편만 (공개·끝난 편은 올리지 않는다)
            media.update(media_files(d, doc_id))
    return media


def build(index_text: str | None, ep_dirs: list[str]) -> tuple[dict, list[dict]]:
    docs, problems = {}, []
    if index_text:
        pilot = 0
        for row in parse_index(index_text):
            if not EP_RE.search(row["label"]):
                pilot += 1
            doc_id, doc = index_doc(row, pilot)
            docs[doc_id] = doc
    for d in ep_dirs:
        doc_id, doc = state_doc(d)
        if doc_id is None:
            problems.append(doc)
            continue
        old = docs.get(doc_id)
        if old:  # 상태 블록이 정본. 회차 목록에만 있는 값은 보탠다
            for k in ("work_code", "delivered", "published", "index_status"):
                if old.get(k) and not doc.get(k):
                    doc[k] = old[k]
        docs[doc_id] = doc
    for doc in docs.values():
        doc["content_hash"] = content_hash(doc)
    return docs, problems


def build_outputs(ep_dirs: list[str]) -> dict:
    """상태 블록이 있는 편마다 BRIEF.md 결과물 문서를 만든다. 키는 `<EP>-s<절 번호>`."""
    tmpl_text = None
    if os.path.isfile(TEMPLATE_BRIEF):
        with open(TEMPLATE_BRIEF, encoding="utf-8") as f:
            tmpl_text = f.read()
    tmpl = template_keys(tmpl_text)
    outs = {}
    for d in ep_dirs:
        doc_id, _ = state_doc(d)
        if doc_id:
            outs.update(output_docs(d, doc_id, tmpl))
    return outs


def changed_ids(docs: dict, committed: dict) -> list[str]:
    return [i for i, d in docs.items() if committed.get(i) != d["content_hash"]]


# ---------- 파일 ----------

def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def check_out(out: str) -> str | None:
    out = os.path.abspath(out)
    inside = os.path.commonpath([out, ROOT]) == ROOT
    if inside and not out.startswith(os.path.join(ROOT, "_scratch")):
        return None
    return out


def cmd_build(out: str, index_arg: str, all_docs: bool, by: str) -> int:
    index_path = index_arg if os.path.isabs(index_arg) else os.path.join(ROOT, index_arg)
    index_text = None
    if os.path.isfile(index_path):
        with open(index_path, encoding="utf-8") as f:
            index_text = f.read()
    dirs = es.episode_dirs()
    docs, problems = build(index_text, dirs)
    outs = build_outputs(dirs)
    media = build_media(dirs)
    committed = read_json(os.path.join(out, CACHE), {})
    changed = list(docs) if all_docs else changed_ids(docs, committed)
    out_committed = {k[len(OUT_PREFIX):]: v for k, v in committed.items() if k.startswith(OUT_PREFIX)}
    out_changed = list(outs) if all_docs else changed_ids(outs, out_committed)
    removed = sorted(set(k for k in committed if not k.startswith((OUT_PREFIX, "media/"))) - set(docs))
    out_removed = sorted(set(out_committed) - set(outs))
    media_committed = {k[len(MEDIA_PREFIX):]: v for k, v in committed.items() if k.startswith(MEDIA_PREFIX)}
    media_new = [i for i, m in media.items() if all_docs or media_committed.get(i) != m["sha"]]
    stamp = now_iso()

    writes = []
    for doc_id, doc in sorted(docs.items(), key=lambda kv: kv[1]["order"], reverse=True):
        path = os.path.join(out, "episodes", f"{doc_id}.json")
        write_json(path, doc)
        if doc_id in changed:
            writes.append({"op": "set", "collection": "episodes", "doc_id": doc_id, "file_path": path})
    for doc_id, doc in sorted(outs.items()):
        path = os.path.join(out, "outputs", f"{doc_id}.json")
        write_json(path, doc)
        if doc_id in out_changed:
            writes.append({"op": "set", "collection": "outputs", "doc_id": doc_id, "file_path": path})
    live = [d for d in docs.values() if d["source"] == "state" and d.get("status") != "done"]
    waiting = sum(len(d.get("pending_operator") or []) for d in live)
    meta = {"synced_at": stamp, "by": by, "live": len(live), "waiting_decisions": waiting,
            "note": f"진행 중 {len(live)}편 · 대표 결정 {waiting}건 · 바뀐 문서 {len(changed) + len(out_changed)}건"}
    meta_path = os.path.join(out, "meta", "sync.json")
    write_json(meta_path, meta)
    writes.append({"op": "set", "collection": "meta", "doc_id": "sync", "file_path": meta_path})
    if changed or out_changed:
        log_id = "sync-" + stamp[:16].replace("-", "").replace(":", "").replace("T", "-")
        log_path = os.path.join(out, "log", f"{log_id}.json")
        allc = sorted(changed, reverse=True) + [f"{o} 결과물" for o in sorted(out_changed)]
        names = ", ".join(allc[:6]) + (" 외" if len(allc) > 6 else "")
        write_json(log_path, {"at": stamp, "by": by, "episode": None, "text": f"동기화: {names} 갱신"})
        writes.append({"op": "set", "collection": "log", "doc_id": log_id, "file_path": log_path})

    write_json(os.path.join(out, "batch.json"), writes)
    hashes = {i: d["content_hash"] for i, d in docs.items()}
    hashes.update({OUT_PREFIX + i: d["content_hash"] for i, d in outs.items()})
    hashes.update({MEDIA_PREFIX + i: m["sha"] for i, m in media.items()})
    write_json(os.path.join(out, MEDIA_UPLOAD), [{"doc_id": i, **media[i]} for i in sorted(media_new)])
    write_json(os.path.join(out, LAST), hashes)
    write_json(os.path.join(out, "manifest.json"), {
        "synced_at": stamp, "index_used": bool(index_text), "docs": len(docs), "changed": changed,
        "outputs": len(outs), "outputs_changed": out_changed, "outputs_removed": out_removed,
        "media": len(media), "media_to_upload": sorted(media_new),
        "removed_from_source": removed, "batch_writes": len(writes), "problems": problems})
    print(f"문서 {len(docs)}개 중 바뀐 것 {len(changed)}개, 결과물 {len(outs)}개 중 바뀐 것 {len(out_changed)}개"
          f" → batch.json 쓰기 {len(writes)}건 ({out})")
    if media_new:
        print(f"[그림] 보드에 올릴 그림 {len(media_new)}장 → {MEDIA_UPLOAD} (올린 뒤 media-batch로 문서를 만든다)")
    if removed:
        print(f"[알림] 원본에서 사라진 문서: {', '.join(removed)} — 보드에서 지울지는 대표에게 확인")
    if out_removed:
        print(f"[알림] BRIEF.md에서 사라진 결과물: {', '.join(out_removed)} — 보드에서 지울지는 대표에게 확인")
    for p in problems:
        print(f"[경고] {p['path']}: {p.get('error')}")
    return 0


def cmd_media_batch(out: str, map_path: str) -> int:
    """올린 그림의 자산 id 대응표({파일 경로: 자산 id 또는 {asset, caption}})로 media 문서 쓰기 묶음을 만든다."""
    pending = read_json(os.path.join(out, MEDIA_UPLOAD), None)
    amap = read_json(map_path, None)
    if pending is None or amap is None:
        print("[오류] build를 먼저 하고, 대응표(JSON)를 준다.", file=sys.stderr)
        return 2

    def norm(x):
        return os.path.normcase(os.path.abspath(x))

    amap = {norm(k): v for k, v in amap.items()}
    writes, missing, stamp = [], [], now_iso()
    for m in pending:
        v = amap.get(norm(m["file"]))
        if v is None:
            missing.append(m["path"])
            continue
        asset, cap = (v, None) if isinstance(v, str) else (v.get("asset"), v.get("caption"))
        doc = {k: m[k] for k in ("episode", "stage", "rel", "path", "sha")}
        doc.update({"caption": cap or m["caption"], "asset": asset, "uploaded_at": stamp})
        path = os.path.join(out, "media", f"{m['doc_id']}.json")
        write_json(path, doc)
        writes.append({"op": "set", "collection": "media", "doc_id": m["doc_id"], "file_path": path})
    write_json(os.path.join(out, "media_batch.json"), writes)
    note = f" · 대응표에 없음 {len(missing)}: {', '.join(missing)}" if missing else ""
    print(f"media 문서 {len(writes)}건 → media_batch.json{note}")
    return 0 if not missing else 1


def cmd_commit(out: str) -> int:
    last = read_json(os.path.join(out, LAST), None)
    if last is None:
        print("[오류] 먼저 build를 실행한다.", file=sys.stderr)
        return 2
    write_json(os.path.join(out, CACHE), last)
    print(f"기준 저장: 문서 {len(last)}개. 다음 build는 이 기준과 비교한다.")
    return 0


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="제작 보드 문서·쓰기 묶음 만들기 (파일만 씀)")
    ap.add_argument("cmd", nargs="?", default="build", choices=("build", "commit", "media-batch"))
    ap.add_argument("--map", help="media-batch: 올린 그림 → 자산 id 대응표 JSON")
    ap.add_argument("--out", required=True, help="출력 폴더 (Git 밖, 예: 에이전트 스크래치)")
    ap.add_argument("--index", default=DEFAULT_INDEX, help="회차 목록 사본 경로 (없으면 건너뜀)")
    ap.add_argument("--all", action="store_true", help="바뀌지 않은 문서도 모두 batch에 담기")
    ap.add_argument("--by", default="Claude", help="동기화 주체 이름 (보드 표시용)")
    args = ap.parse_args(argv)
    out = check_out(args.out)
    if out is None:
        print("[오류] 출력 폴더는 저장소 밖이나 _scratch/ 아래여야 한다(채널 정보가 Git에 들어가지 않게).",
              file=sys.stderr)
        return 2
    if args.cmd == "commit":
        return cmd_commit(out)
    if args.cmd == "media-batch":
        return cmd_media_batch(out, args.map or "")
    return cmd_build(out, args.index, args.all, args.by)


if __name__ == "__main__":
    sys.exit(main())
