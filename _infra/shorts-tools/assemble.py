#!/usr/bin/env python3
"""쇼츠 조립 v2 — 내레이션 기준 타이밍, 잉크 마크, 숫자 카드, 자막, 효과음, 계측.

사용: python3 _infra/shorts-tools/assemble.py productions/shorts/<EP>/assemble.json [--preview] [--words-only]
매니페스트 안의 상대경로는 매니페스트 파일 위치 기준이다. --preview는 540×960, 빠른 인코딩.
--words-only는 내레이션 무음 제거와 Whisper 단어 시각만 out/_work/words_bNN.json에 캐시한다
(Whisper가 있는 기계에서 먼저 돌리고, 렌더는 캐시를 가져간 다른 기계에서 해도 된다).

{
 "fps": 24, "W": 1080, "H": 1920, "lang": "ko",
 "font": "<Pretendard ExtraBold 경로>", "card_font": "<손글씨 폰트 경로>",
 "lead": 0.15, "tail": 0.35, "cut_shift": -0.08, "crf": 19, "voice_block_lufs": -18, "last_sub_hold": 0.3,
 "foley_db": -30, "sfx_db": -24, "bgm": null, "bgm_db": -30, "target_lufs": -16,
 "board_tone": [224, 224, 218],     # 선택: 샷마다 보드 바탕색을 이 색으로 맞춤(배율 0.88~1.12)
 "emph": ["강조어"], "emph_color": "#FFD23F",
 "sub_style": {"size": 68, "outline": 7, "bottom": 538, "max_chars": 14},
 "out": "out/final.mp4",
 "blocks": [{
   "n": 1, "voice": "voices/b01.mp3", "vo_line": "TTS 문구 그대로",
   "dur": null,                       # 없으면 lead + 발화 + tail
   "subs": [["화면 자막", "그 자막이 읽는 TTS 문구"]],   # 없으면 vo_line을 잘라 씀
   "shots": [{
     "file": "clips/x.mp4 | refs/x.png", "at": "TTS 부분 문자열 | 블록 기준 초",  # 첫 샷은 0
     "start": 0.0, "speed": 1.0, "clip_end": null, "freeze_prev": false,  # freeze_prev: 앞 샷 클립의 마지막 프레임에서 정지
     "xfade": 0.0,                      # 앞 샷에서 디졸브로 넘어오는 시간(초)
     "kb": [1.0, 1.05], "focus": [0.5, 0.35], "foley_db": -30,
     "patch": [[x0, y0, x1, y1]],       # 정지 컷의 가짜 글자 등을 빈 보드로 지움
     "marks": [{"type": "x|circle|underline|arrow|dim|bracket", "box": [x, y, w, h], "side": "bottom|left|right",
                "from": [x, y], "to": [x, y], "at": "...", "color": "red|blue|#hex", "dur": 0.35, "screen": false}],
     "offset": [dx, dy],                # 화면을 옮겨 피사체를 안전 영역으로 (빈 곳은 보드 배경으로 채움)
     "place": {"scale": [0.85, 0.88], "x": 0.04, "y": 0.0, "crop_bottom": 0.955},  # 축소 배치(kb 대신)
     "cards": [{"text": "108mm", "at": "...", "pos": [0.5, 0.6], "size": 150, "color": "blue", "plate": false}]
   }]
 }]
}
좌표는 모두 원본 그림 기준 비율(0~1). 마크는 줌을 따라 움직이고, 카드·자막은 화면에 고정된다. 시각 "at"은 vo_line 안의 부분 문자열(그 말이 시작되는 순간) 또는 블록 시작 기준 초.

외부 호출: ffmpeg/ffprobe, faster-whisper(있으면). 네트워크는 Whisper 모델 첫 다운로드 때만.
"""
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
SR = 48000
COLORS = {"red": "#E0322B", "blue": "#1F4FD8", "black": "#1E1E1E", "green": "#1E9E4A",
          "soft_red": "#D9604F", "soft_blue": "#3E64C2", "soft_green": "#5E9E6E"}


class AsmError(Exception):
    pass


def ff(args, what):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args,
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise AsmError(f"{what} 실패: {r.stderr.strip()[-800:]}")
    return r


def probe_dur(path, stream=None):
    args = ["ffprobe", "-v", "error"]
    if stream:
        args += ["-select_streams", stream, "-show_entries", "stream=duration"]
    else:
        args += ["-show_entries", "format=duration"]
    r = subprocess.run(args + ["-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip().splitlines()[0])
    except Exception:  # noqa
        return 0.0


def has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True)
    return bool(r.stdout.strip())


def color(c, alpha=255):
    h = COLORS.get(c, c).lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


# ---------- 오디오 입출력 ----------

def read_audio(path, dur=None, start=0.0, speed=1.0):
    """ffmpeg로 48k 스테레오 float32 배열을 읽는다."""
    af = []
    if abs(speed - 1.0) > 1e-3:
        af.append(f"atempo={speed:.4f}")
    args = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", path, "-vn"]
    if af:
        args += ["-af", ",".join(af)]
    if dur:
        args += ["-t", f"{dur:.4f}"]
    args += ["-ac", "2", "-ar", str(SR), "-f", "f32le", "-"]
    r = subprocess.run(args, capture_output=True, check=False)
    a = np.frombuffer(r.stdout, dtype=np.float32)
    return a[: a.size // 2 * 2].reshape(-1, 2).copy()


def write_wav(path, a):
    a = np.clip(a, -1, 1)
    pcm = (a * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def db(x):
    return 10 ** (x / 20.0)


def place(bus, clip, t):
    i = int(round(t * SR))
    if i >= len(bus) or len(clip) == 0:
        return
    n = min(len(clip), len(bus) - i)
    bus[i:i + n] += clip[:n]


# ---------- 합성 효과음 ----------

def sfx_marker(dur, strokes=1, seed=0):
    """마커 끽: 대역 잡음 + 획마다 엔벨로프."""
    rng = np.random.default_rng(seed)
    n = max(1, int(dur * SR))
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    X *= np.exp(-((f - 3200) / 1400) ** 2)
    x = np.fft.irfft(X, n)
    env = np.zeros(n)
    seg = n // strokes
    for k in range(strokes):
        m = seg - int(0.03 * SR)
        if m <= 0:
            continue
        tt = np.linspace(0, 1, m)
        e = np.sin(np.pi * tt) ** 0.6 * (0.75 + 0.25 * np.sin(2 * np.pi * 9 * tt + k))
        env[k * seg:k * seg + m] = e
    y = x * env
    y /= (np.abs(y).max() or 1)
    return np.stack([y, y], 1) * 0.5


def sfx_pop():
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    fr = 950 * np.exp(-t * 18) + 220
    ph = 2 * np.pi * np.cumsum(fr) / SR
    y = np.sin(ph) * np.exp(-t * 38)
    y[:40] += np.linspace(0.6, 0, 40)
    y /= np.abs(y).max()
    return np.stack([y, y], 1) * 0.5


# ---------- 내레이션 ----------

def trim_voice(src, out):
    af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
          "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse")
    ff(["-i", src, "-af", af, "-ac", "1", "-ar", str(SR), out], f"무음 제거 {src}")
    return probe_dur(out)


def loudnorm_two_pass(src, out, lufs, tp=-1.5):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af",
                        f"loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise AsmError("loudnorm 1차 측정 실패")
    j = json.loads(m.group(0))
    af = (f"loudnorm=I={lufs}:TP={tp}:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
          f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:"
          f"linear=true,aresample={SR}")
    ff(["-i", src, "-af", af, "-ac", "2", "-ar", str(SR), out], "loudnorm 2차")


def measure_lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    li = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(li[-1]) if li else None


def norm_chars(s):
    return re.sub(r"[\s\.,!?…·\"'“”‘’()\-~:;]", "", s)


def whisper_words(model, path, lang, prompt=None):
    # 대본을 initial_prompt로 주면 숫자를 대본처럼 한글로 받아써서 글자 순번 정렬이 정확해진다
    segs, _ = model.transcribe(path, language=lang, word_timestamps=True, vad_filter=False,
                               initial_prompt=prompt or None)
    return [(w.word, float(w.start), float(w.end)) for s in segs for w in (s.words or [])]


def char_timeline(words, script=None, speech_len=None):
    """Whisper 단어 시각 → 문자별 시각. script(대본)를 주면 difflib로 대본 문자에 맞춰 정렬하고,
    받아쓰기와 다른 부분(숫자 표기, 빠진 단어)은 양옆 일치 지점 사이를 비례로 채운다."""
    tl, wn = [], []
    for text, s, e in words:
        cs = norm_chars(text)
        if not cs:
            continue
        step = (e - s) / len(cs)
        tl.extend((s + i * step, s + (i + 1) * step) for i in range(len(cs)))
        wn.extend(cs)
    if not script or not tl:
        return tl
    import difflib
    sn = norm_chars(script)
    sm = difflib.SequenceMatcher(None, sn, "".join(wn), autojunk=False)
    m = [None] * len(sn)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            m[a + k] = tl[b + k]
    end_t = max(tl[-1][1], speech_len or 0)
    out, i = [], 0
    while i < len(sn):
        if m[i] is not None:
            out.append(m[i])
            i += 1
            continue
        j = i
        while j < len(sn) and m[j] is None:
            j += 1
        t0 = out[-1][1] if out else 0.0
        t1 = m[j][0] if j < len(sn) else end_t
        n = j - i
        step = max(0.0, t1 - t0) / n
        out.extend((t0 + k * step, t0 + (k + 1) * step) for k in range(n))
        i = j
    return out


class Clock:
    """블록 하나의 TTS 문자 → 시각 사상 (대본 정렬된 문자 시각, 길이가 다르면 비례)."""

    def __init__(self, vo_line, tl, speech_len, offset):
        self.norm = norm_chars(vo_line or "")
        self.total = max(len(self.norm), 1)
        self.tl, self.sp, self.off, self.line = tl, speech_len, offset, vo_line or ""

    def at_index(self, a, end=False):
        if self.tl:
            i = min(len(self.tl) - 1, int(round(a * (len(self.tl) - 1) / max(self.total - 1, 1))))
            return self.off + (self.tl[i][1] if end else self.tl[i][0])
        return self.off + self.sp * (a + (1 if end else 0)) / self.total

    def cue(self, c, block_start):
        """블록 기준 시각(초)을 돌려준다."""
        if isinstance(c, (int, float)):
            return float(c)
        pos = self.line.find(c)
        if pos < 0:
            raise AsmError(f"자막/큐 문구가 vo_line에 없음: {c!r}")
        a = len(norm_chars(self.line[:pos]))
        return self.at_index(a) - block_start

    def span(self, tts_text, from_char):
        n = len(norm_chars(tts_text))
        return self.at_index(from_char), self.at_index(from_char + max(n, 1) - 1, end=True), from_char + n


def chunk_line(text, max_chars):
    words, chunks, cur = text.split(), [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if cur and len(cand) > max_chars:
            chunks.append(cur)
            cur = w
        else:
            cur = cand
        if re.search(r"[,.?!…]$", cur) and len(cur) >= max_chars * 0.5:
            chunks.append(cur)
            cur = ""
    if cur:
        chunks.append(cur)
    if len(chunks) > 1 and len(chunks[-1]) < 5:
        tail = chunks.pop()
        chunks[-1] += " " + tail
    return chunks


# ---------- 그리기 ----------

def jitter_path(pts, amp, rng):
    return [(x + rng.uniform(-amp, amp), y + rng.uniform(-amp, amp)) for x, y in pts]


def resample(pts, n):
    d = [0.0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        d.append(d[-1] + math.hypot(x1 - x0, y1 - y0))
    L = d[-1] or 1.0
    out, j = [], 0
    for k in range(n):
        s = L * k / (n - 1)
        while j < len(d) - 2 and d[j + 1] < s:
            j += 1
        seg = (d[j + 1] - d[j]) or 1.0
        u = (s - d[j]) / seg
        (x0, y0), (x1, y1) = pts[j], pts[j + 1]
        out.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u))
    return out


def mark_strokes(m, W, H, seed):
    """마크 → 획 목록(픽셀 좌표 점열). 손그림 느낌으로 흔든다."""
    rng = random.Random(seed)
    t = m["type"]
    strokes = []
    if "box" in m:
        x, y, w, h = m["box"]
        x, y, w, h = x * W, y * H, w * W, h * H
    if t == "x":
        strokes = [resample([(x, y), (x + w, y + h)], 24), resample([(x + w, y), (x, y + h)], 24)]
    elif t == "circle":
        cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
        a0 = math.radians(-110)
        pts = []
        for k in range(73):
            a = a0 + 2 * math.pi * 1.08 * k / 72
            wob = 1 + 0.05 * math.sin(3 * a + 1.3) + 0.03 * (k / 72)
            pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a)))
        strokes = [pts]
    elif t == "underline":
        pts = [(x + w * k / 30, y + h + 6 * math.sin(k / 30 * math.pi * 2.2)) for k in range(31)]
        strokes = [pts]
    elif t == "bracket":
        side = m.get("side", "bottom")
        if side == "right":
            dep = min(w, h) * 0.25
            pts = [(x + w - dep, y), (x + w, y), (x + w, y + h), (x + w - dep, y + h)]
        elif side == "left":
            dep = min(w, h) * 0.25
            pts = [(x + dep, y), (x, y), (x, y + h), (x + dep, y + h)]
        else:
            dep = min(w, h) * 0.18
            pts = [(x, y + h - dep), (x, y + h), (x + w, y + h), (x + w, y + h - dep)]
        strokes = [resample(pts, 40)]
    elif t in ("arrow", "dim"):
        (x0, y0), (x1, y1) = m["from"], m["to"]
        x0, y0, x1, y1 = x0 * W, y0 * H, x1 * W, y1 * H
        bend = m.get("bend", 0.12)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        nx, ny = -(y1 - y0), (x1 - x0)
        cx, cy = mx + nx * bend, my + ny * bend
        pts = []
        for k in range(41):
            u = k / 40
            pts.append(((1 - u) ** 2 * x0 + 2 * (1 - u) * u * cx + u * u * x1,
                        (1 - u) ** 2 * y0 + 2 * (1 - u) * u * cy + u * u * y1))
        strokes = [pts]
        head = max(28, 0.045 * W)

        def heads(px, py, qx, qy):
            ang = math.atan2(qy - py, qx - px)
            return [[(qx, qy), (qx - head * math.cos(ang - 0.5), qy - head * math.sin(ang - 0.5))],
                    [(qx, qy), (qx - head * math.cos(ang + 0.5), qy - head * math.sin(ang + 0.5))]]
        strokes += heads(pts[-3][0], pts[-3][1], pts[-1][0], pts[-1][1])
        if t == "dim":
            strokes += heads(pts[2][0], pts[2][1], pts[0][0], pts[0][1])
    else:
        raise AsmError(f"알 수 없는 마크: {t}")
    amp = 2.2
    return [jitter_path(s, amp, rng) for s in strokes]


def draw_partial(draw, strokes, p, width, fill):
    """p(0~1)만큼 획을 순서대로 그린다."""
    lens = []
    for s in strokes:
        lens.append(sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(s, s[1:])))
    total = sum(lens) or 1.0
    budget = total * max(0.0, min(1.0, p))
    r = width / 2
    for s, L in zip(strokes, lens):
        if budget <= 0:
            break
        pts = [s[0]]
        acc = 0.0
        for a, b in zip(s, s[1:]):
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            if acc + d <= budget:
                pts.append(b)
                acc += d
            else:
                u = (budget - acc) / (d or 1)
                pts.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
                acc = budget
                break
        budget -= L
        if len(pts) >= 2:
            draw.line(pts, fill=fill, width=int(width), joint="curve")
        for q in (pts[0], pts[-1]):
            draw.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=fill)


def ease_out(u):
    u = max(0.0, min(1.0, u))
    return 1 - (1 - u) ** 3


class CardArt:
    def __init__(self, card, font_path, W, H):
        size = int(card.get("size", 170) * W / 1080)
        font = ImageFont.truetype(font_path, size)
        col = color(card.get("color", "blue"))
        pad = int(size * 0.25)
        bb = font.getbbox(card["text"], stroke_width=int(size * 0.07))
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        im = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if card.get("plate"):  # 복잡한 그림 위에서는 보드색 바탕판을 깔아 읽히게 한다
            d.rounded_rectangle((pad // 3, pad // 3, im.width - pad // 3, im.height - pad // 3),
                                radius=pad, fill=(248, 248, 245, 236))
        d.text((pad - bb[0], pad - bb[1]), card["text"], font=font, fill=col,
               stroke_width=int(size * 0.07), stroke_fill=(255, 255, 255, 255))
        self.im = im.rotate(card.get("tilt", -3), resample=Image.BICUBIC, expand=True)
        self.cx, self.cy = card.get("pos", [0.5, 0.6])
        self.cx, self.cy = self.cx * W, self.cy * H

    def paste(self, layer, u):
        """u: 등장 후 경과(초)."""
        k = min(1.0, max(0.0, u / 0.22))
        s = 1.0 if k >= 1 else 0.5 + 0.5 * ease_out(k) + 0.18 * math.sin(math.pi * k)
        im = self.im if abs(s - 1) < 1e-3 else self.im.resize(
            (max(1, int(self.im.width * s)), max(1, int(self.im.height * s))), Image.BICUBIC)
        layer.alpha_composite(im, (int(self.cx - im.width / 2), int(self.cy - im.height / 2)))


class SubArt:
    def __init__(self, text, M, font_path, W, H):
        st = M.get("sub_style", {})
        size = int(st.get("size", 68) * W / 1080)
        ow = max(2, int(st.get("outline", 7) * W / 1080))
        font = ImageFont.truetype(font_path, size)
        while font.getlength(text) > W - 2 * int(60 * W / 1080) and size > 30:
            size -= 2
            font = ImageFont.truetype(font_path, size)
        emph = M.get("emph", [])
        ecol = color(M.get("emph_color", "#FFD23F"))
        runs, i = [], 0
        pat = "|".join(re.escape(e) for e in sorted(emph, key=len, reverse=True)) if emph else None
        if pat:
            for mm in re.finditer(pat, text):
                if mm.start() > i:
                    runs.append((text[i:mm.start()], (255, 255, 255, 255)))
                runs.append((mm.group(0), ecol))
                i = mm.end()
        runs.append((text[i:], (255, 255, 255, 255)))
        tw = int(font.getlength(text))
        asc, desc = font.getmetrics()
        im = Image.new("RGBA", (tw + ow * 4, asc + desc + ow * 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x = ow * 2
        for t, c in runs:
            if not t:
                continue
            d.text((x, ow * 2), t, font=font, fill=c, stroke_width=ow, stroke_fill=(24, 24, 24, 255))
            x += font.getlength(t)
        self.im = im
        self.x = (W - im.width) // 2
        self.y = H - int(st.get("bottom", 538) * H / 1920) - im.height


# ---------- 영상 프레임 소스 ----------

def board_background(a, block=24):
    """잉크(채도 있거나 어두운 픽셀과 그 주변)를 빼고 보드 배경만 부드럽게 추정한다."""
    from PIL import ImageFilter
    h, w = a.shape[:2]
    mx, mn = a.max(2), a.min(2)
    ink = ((mx - mn) > 14) | (mx < 205)
    ink = np.asarray(Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(31))) > 0
    x = a.copy()
    x[ink] = np.nan
    hb, wb = h // block, w // block
    Xb = x[:hb * block, :wb * block].reshape(hb, block, wb, block, 3)
    valid = ~np.isnan(Xb[..., 0])
    cnt = valid.sum((1, 3))
    ok = cnt > block * block * 0.2
    import warnings as _w
    with np.errstate(invalid="ignore"), _w.catch_warnings():
        _w.simplefilter("ignore", RuntimeWarning)
        small = np.where(ok[..., None], np.nanmedian(np.where(valid[..., None], Xb, np.nan).transpose(0, 2, 1, 3, 4)
                                                     .reshape(hb, wb, -1, 3), axis=2), 0)
    for _ in range(400):  # 빈 칸은 이웃 평균으로 채운다
        if ok.all():
            break
        pad = np.pad(small * ok[..., None], ((1, 1), (1, 1), (0, 0)))
        pk = np.pad(ok.astype(np.float32), 1)
        ssum = sum(pad[1 + dy:1 + dy + hb, 1 + dx:1 + dx + wb] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        scnt = sum(pk[1 + dy:1 + dy + hb, 1 + dx:1 + dx + wb] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        newok = (~ok) & (scnt > 0)
        small[newok] = ssum[newok] / scnt[newok][:, None]
        ok = ok | newok
    bg = Image.fromarray(np.clip(small, 0, 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    return np.asarray(bg).astype(np.float32)


def board_patch(im, rect, seed=0):
    """보드 위 영역을 빈 보드처럼 지운다(배경 추정으로 채움 + 옅은 지우개 자국)."""
    a = np.asarray(im).astype(np.float32)
    h, w = a.shape[:2]
    x0, y0, x1, y1 = int(rect[0] * w), int(rect[1] * h), int(rect[2] * w), int(rect[3] * h)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    bg = board_background(a)
    fill = bg[y0:y1, x0:x1].copy()
    rng = np.random.default_rng(seed)
    fill += rng.normal(0, 1.0, fill.shape)
    yy, xx = np.mgrid[0:y1 - y0, 0:x1 - x0]
    for _ in range(3):  # 지우개 자국
        cy, cx = rng.uniform(0.2, 0.8) * (y1 - y0), rng.uniform(0.2, 0.8) * (x1 - x0)
        ry, rx = rng.uniform(0.08, 0.2) * (y1 - y0) + 8, rng.uniform(0.25, 0.45) * (x1 - x0)
        g = np.exp(-(((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2))
        fill -= (g * rng.uniform(3, 6))[..., None]
    f = 12  # 경계 페더
    m = np.ones((y1 - y0, x1 - x0), np.float32)
    ramp = np.linspace(0, 1, f)
    if y0 > 0:
        m[:f] *= ramp[:, None]
    if y1 < h:
        m[-f:] *= ramp[::-1][:, None]
    if x0 > 0:
        m[:, :f] *= ramp[None, :]
    if x1 < w:
        m[:, -f:] *= ramp[::-1][None, :]
    reg = a[y0:y1, x0:x1]
    a[y0:y1, x0:x1] = reg * (1 - m[..., None]) + fill * m[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


class StillSource:
    def __init__(self, path, W, H, kb, patches=()):
        im = Image.open(path).convert("RGB")
        for i, r in enumerate(patches):
            im = board_patch(im, r, seed=i + 1)
        zmax = max(kb)
        tw, th = int(W * zmax), int(H * zmax)
        sc = max(tw / im.width, th / im.height)
        im = im.resize((max(tw, int(im.width * sc)), max(th, int(im.height * sc))), Image.LANCZOS)
        self.im, self.W, self.H = im, W, H

    def frame(self, k):
        return self.im


class ClipSource:
    def __init__(self, path, W, H, start, speed, nf, fps, clip_end=None):
        vf = (f"setpts=PTS/{speed:.4f},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop={W}:{H},fps={fps}")
        lim = ["-t", f"{max(0.05, clip_end - start):.3f}"] if clip_end else []
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"] + lim + ["-i", path, "-an", "-vf", vf,
                            "-frames:v", str(nf), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                           capture_output=True, check=False)
        n = len(r.stdout) // (W * H * 3)
        if n == 0:
            raise AsmError(f"클립 디코딩 실패: {path}")
        self.buf, self.n, self.W, self.H = r.stdout, n, W, H
        self.held = max(0, nf - n)

    def frame(self, k):
        k = min(k, self.n - 1)
        o = k * self.W * self.H * 3
        return Image.frombuffer("RGB", (self.W, self.H), self.buf[o:o + self.W * self.H * 3], "raw", "RGB", 0, 1)


def apply_offset(fr, dx, dy, bg, feather=48):
    """보기 화면을 (dx, dy)만큼 옮기고, 드러난 곳은 보드 배경으로 채운다."""
    W, H = fr.size
    ox, oy = int(round(dx * W)), int(round(dy * H))
    mask = Image.new("L", (W, H), 255)
    md = ImageDraw.Draw(mask)
    for k in range(feather):  # 화면 안쪽으로 들어온 가장자리만 부드럽게
        a = int(255 * (k + 1) / (feather + 1))
        if ox < 0:
            md.line([(W - 1 - k, 0), (W - 1 - k, H)], fill=a)
        if ox > 0:
            md.line([(k, 0), (k, H)], fill=a)
        if oy < 0:
            md.line([(0, H - 1 - k), (W, H - 1 - k)], fill=a)
        if oy > 0:
            md.line([(0, k), (W, k)], fill=a)
    out = bg.copy()
    out.paste(fr, (ox, oy), mask)
    return out


def view_box(z, focus):
    """줌 z(≥1), 초점 focus → 원본 기준 정규화 보기 상자 (x0, y0, w, h)."""
    c = 1.0 / z
    x0 = min(max(0.0, focus[0] - c / 2), 1 - c)
    y0 = min(max(0.0, focus[1] - c / 2), 1 - c)
    return x0, y0, c, c


def tone_gain(im, target):
    """보드 바탕(밝은 부분) 중앙값을 target 색에 맞추는 채널별 배율. 샷마다 한 번 재고 그 샷 전체에 쓴다."""
    a = np.asarray(im.convert("RGB"), dtype=np.float32)
    a = a[: int(a.shape[0] * 0.7)]
    lum = a.mean(-1)
    m = (lum > 170) & (lum < 252)
    if m.sum() < 1000:
        return None
    med = np.median(a[m], axis=0)
    return np.clip(np.array(target, np.float32) / np.maximum(med, 1), 0.88, 1.12)


def apply_gain(im, g):
    a = np.asarray(im.convert("RGB"), dtype=np.float32) * g
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def kb_view(src_im, W, H, z, focus):
    """줌 z(≥1)로 focus 근처를 잘라 W×H로."""
    iw, ih = src_im.size
    vx, vy, vc, _ = view_box(z, focus)
    x0, y0, cw, ch = vx * iw, vy * ih, vc * iw, vc * ih
    box = (x0, y0, x0 + cw, y0 + ch)
    if abs(cw - W) < 0.5 and abs(ch - H) < 0.5 and x0 == int(x0) and y0 == int(y0):
        return src_im.crop(tuple(int(v) for v in box))
    return src_im.resize((W, H), Image.BICUBIC, box=box)


# ---------- 본체 ----------

def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    preview = "--preview" in argv
    words_only = "--words-only" in argv
    argv = [a for a in argv if a not in ("--preview", "--words-only")]
    if len(argv) != 1:
        print(__doc__)
        return 2
    mpath = os.path.abspath(argv[0])
    base = os.path.dirname(mpath)
    with open(mpath, encoding="utf-8") as f:
        M = json.load(f)
    fps = M.setdefault("fps", 24)
    W0, H0 = M.setdefault("W", 1080), M.setdefault("H", 1920)
    W, H = (W0 // 2, H0 // 2) if preview else (W0, H0)
    P = lambda p: p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))  # noqa: E731
    out = P(M.get("out", "out/final.mp4"))
    if preview:
        out = os.path.splitext(out)[0] + "_preview.mp4"
    work = os.path.join(os.path.dirname(out), "_work")
    os.makedirs(work, exist_ok=True)
    warnings, qc_fail = [], []
    lead_d, tail_d = M.get("lead", 0.15), M.get("tail", 0.35)
    cut_shift = M.get("cut_shift", -0.08)

    _model = {}

    def get_model():
        """Whisper는 캐시가 없을 때만 불러온다."""
        if "m" not in _model:
            _model["m"] = None
            if not M.get("no_whisper"):
                try:
                    from faster_whisper import WhisperModel
                    _model["m"] = WhisperModel(M.get("whisper_model", "small"), device="cpu", compute_type="int8")
                except Exception as e:  # noqa
                    warnings.append(f"Whisper 사용 불가 → 비례 타이밍 ({e.__class__.__name__}) — 납품 금지")
        return _model["m"]

    # 1) 블록 길이와 내레이션
    t0, plan = 0.0, []
    for b in M["blocks"]:
        lead = b.get("lead", lead_d)
        tail = b.get("tail", tail_d)
        tv, sp, tl = None, None, []
        if b.get("voice"):
            tv = os.path.join(work, f"voice_b{b['n']:02d}.wav")
            sp = trim_voice(P(b["voice"]), tv)
            cache = os.path.join(work, f"words_b{b['n']:02d}.json")
            with open(P(b["voice"]), "rb") as vf:
                key = hashlib.sha256(vf.read()).hexdigest() + "|p1|" + hashlib.sha256(
                    b.get("vo_line", "").encode("utf-8")).hexdigest()[:12]
            words = None
            if os.path.isfile(cache):
                with open(cache, encoding="utf-8") as f:
                    cj = json.load(f)
                if cj.get("key") == key:
                    words = cj["words"]
            if words is None and get_model():
                words = whisper_words(get_model(), tv, M.get("lang", "ko"), b.get("vo_line"))
                with open(cache, "w", encoding="utf-8") as f:
                    json.dump({"key": key, "words": words}, f, ensure_ascii=False)
            if words:
                tl = char_timeline(words, b.get("vo_line", ""), sp)
            dur = b.get("dur") or (lead + sp + tail)
            if sp + lead > dur:
                qc_fail.append(f"블록 {b['n']} 발화 {sp:.2f}s가 블록 {dur:.2f}s를 넘음")
        else:
            if not b.get("dur"):
                raise AsmError(f"블록 {b['n']}: 내레이션이 없으면 dur 필요")
            dur = b["dur"]
            sp = dur - lead - tail
            warnings.append(f"블록 {b['n']} 내레이션 없음 (임시 길이 {dur}s, 자막 비례 배치)")
        bf = int(round((t0 + dur) * fps)) - int(round(t0 * fps))
        clock = Clock(b.get("vo_line", ""), tl, sp, t0 + lead)
        plan.append(dict(b=b, start=t0, frames=bf, f0=int(round(t0 * fps)), dur=dur, tv=tv, sp=sp,
                         lead=lead, clock=clock))
        t0 += dur
    total_frames = int(round(t0 * fps))
    total = total_frames / fps
    if words_only:  # Whisper 시각만 캐시하고 끝낸다 (렌더는 다른 기계에서)
        print(json.dumps({"words_cached": [pb["b"]["n"] for pb in plan if pb["tv"]],
                          "total_s": round(total, 3), "warnings": warnings}, ensure_ascii=False))
        return 0

    # 2) 샷 경계·마크·카드·자막 시각
    shots, events, subs = [], [], []
    for pb in plan:
        b, clock = pb["b"], pb["clock"]
        starts = []
        for k, s in enumerate(b["shots"]):
            if k == 0:
                starts.append(0.0)
            elif "at" in s:
                tt = clock.cue(s["at"], pb["start"]) + (cut_shift if isinstance(s["at"], str) else 0)
                starts.append(min(max(tt, starts[-1] + 0.4), pb["dur"] - 0.4))
            else:
                starts.append(starts[-1] + b["shots"][k - 1]["dur"])
        for k, s in enumerate(b["shots"]):
            fa = pb["f0"] + int(round(starts[k] * fps))
            fb = pb["f0"] + (int(round(starts[k + 1] * fps)) if k + 1 < len(starts) else pb["frames"])
            if fb - fa < 6:
                warnings.append(f"블록 {b['n']} 샷 {k + 1}이 {fb - fa}프레임뿐")
            shot = dict(s=s, fa=fa, fb=fb, block=b["n"], marks=[], cards=[])
            for j, m in enumerate(s.get("marks", [])):
                ta = pb["start"] + (clock.cue(m["at"], pb["start"]) if "at" in m else starts[k] + m.get("t", 0.25))
                shot["marks"].append(dict(m=m, t=ta, seed=b["n"] * 100 + k * 10 + j))
                events.append(("mark", ta, m))
            for j, c in enumerate(s.get("cards", [])):
                ta = pb["start"] + (clock.cue(c["at"], pb["start"]) if "at" in c else starts[k] + c.get("t", 0.2))
                shot["cards"].append(dict(c=c, t=ta))
                events.append(("card", ta, c))
            shots.append(shot)
        # 자막
        pairs = b.get("subs") or [[c, c] for c in chunk_line(b.get("vo_line", ""),
                                                              M.get("sub_style", {}).get("max_chars", 14))]
        cur, ev = 0, []
        for disp, tts in pairs:
            pos = clock.line.find(tts) if tts else -1
            if pos >= 0:
                cur = len(norm_chars(clock.line[:pos]))
            s_, e_, cur = clock.span(tts, cur)
            ev.append([disp, s_, e_])
        for i in range(len(ev) - 1):
            if ev[i + 1][1] - ev[i][2] < 0.35:
                ev[i][2] = ev[i + 1][1]
        if ev:
            ev[-1][2] = min(ev[-1][2] + b.get("last_sub_hold", M.get("last_sub_hold", 0.3)), pb["start"] + pb["dur"])
        mind = M.get("min_sub", 0.8)
        for i in range(len(ev)):  # 너무 짧은 자막은 늘리고 다음 자막을 그만큼 늦춘다
            if ev[i][2] - ev[i][1] < mind:
                ev[i][2] = ev[i][1] + mind
                if i + 1 < len(ev) and ev[i + 1][1] < ev[i][2]:
                    ev[i + 1][1] = ev[i][2]
                    ev[i + 1][2] = max(ev[i + 1][2], ev[i + 1][1] + 0.5)
        bend = pb["start"] + pb["dur"] - 1.0 / fps
        for e in ev:
            e[2] = min(e[2], bend)
        for disp, s_, e_ in ev:
            if e_ - s_ < 0.7 or e_ - s_ > 3.6:
                warnings.append(f"자막 {e_ - s_:.2f}s: {disp}")
            subs.append((disp, s_, e_))

    # 3) 프레임 합성 → 한 번에 인코딩
    font_sub = P(M["font"])
    font_card = P(M.get("card_font", M["font"]))
    sub_arts = [(SubArt(d, M, font_sub, W, H), s_, e_) for d, s_, e_ in subs]
    vid = os.path.join(work, "video.mp4")
    enc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                            "-c:v", "libx264", "-preset", "ultrafast" if preview else "medium",
                            "-crf", "23" if preview else str(M.get("crf", 19)), "-pix_fmt", "yuv420p", vid],
                           stdin=subprocess.PIPE)
    review = []
    prev_clip = None
    prev_base = None
    tone = M.get("board_tone")  # [r, g, b] — 샷마다 다른 보드 밝기·색온도를 하나로 맞춘다
    tone_cache = {}
    try:
        for sh in shots:
            s = sh["s"]
            nf = sh["fb"] - sh["fa"]
            src = P(s["file"])
            if not os.path.isfile(src):
                raise AsmError(f"샷 파일 없음: {s['file']}")
            kb = s.get("kb", [1.0, 1.0])
            focus = s.get("focus", [0.5, 0.4])
            is_img = os.path.splitext(src)[1].lower() in IMG_EXT
            if is_img:
                srcobj = StillSource(src, W, H, kb, s.get("patch", []))
            else:
                c_start, c_end = s.get("start", 0.0), s.get("clip_end")
                if s.get("freeze_prev") and prev_clip and prev_clip[0] == src:
                    c_start = prev_clip[1]  # 앞 샷이 끝난 그 프레임에서 멈춘다
                    c_end = c_start + 0.05
                srcobj = ClipSource(src, W, H, c_start, s.get("speed", 1.0), nf, fps, c_end)
                if srcobj.held > 3 and not s.get("freeze_prev") and not c_end:
                    warnings.append(f"클립 {s['file']} 마지막 {srcobj.held}프레임 정지 유지")
                used = min(nf, srcobj.n)
                prev_clip = (src, c_start + max(0, used - 1) / fps * s.get("speed", 1.0))
            marks = [dict(x, strokes=mark_strokes(x["m"], W, H, x["seed"])) for x in sh["marks"]]
            cards = [dict(x, art=CardArt(x["c"], font_card, W, H)) for x in sh["cards"]]
            done_cache = {}
            xf_n = int(round(s.get("xfade", 0) * fps))
            base_last = None
            off = s.get("offset", [0.0, 0.0])
            has_off = abs(off[0]) > 1e-4 or abs(off[1]) > 1e-4
            pl = s.get("place")  # {"scale": [a, b], "x": .., "y": .., "crop_bottom": ..} 축소 배치
            static_view = abs(kb[0] - 1) < 1e-3 and abs(kb[1] - 1) < 1e-3 and not has_off and not pl
            off_bg = None
            for k in range(nf):
                gf = sh["fa"] + k
                t = gf / fps
                u = k / max(nf - 1, 1)
                z = kb[0] + (kb[1] - kb[0]) * (0.5 - 0.5 * math.cos(math.pi * u))
                fr = srcobj.frame(k)
                if tone:
                    tk = s["file"]  # src는 아래 place 처리에서 다른 값으로 바뀌므로 파일명을 키로 쓴다
                    if tk not in tone_cache:
                        tone_cache[tk] = tone_gain(fr, tone)
                    if tone_cache[tk] is not None:
                        fr = apply_gain(fr, tone_cache[tk])
                if is_img or abs(z - 1) > 1e-3:
                    fr = kb_view(fr, W, H, z, focus)
                if pl:
                    sc0 = pl.get("scale", [0.85, 0.85])
                    sc = sc0[0] + (sc0[1] - sc0[0]) * (0.5 - 0.5 * math.cos(math.pi * u))
                    cb = pl.get("crop_bottom", 1.0)
                    src = fr.convert("RGB").crop((0, 0, W, int(H * cb)))
                    if off_bg is None:
                        off_bg = Image.fromarray(np.clip(board_background(
                            np.asarray(src).astype(np.float32)), 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
                    sw, shh = int(W * sc), int(H * cb * sc)
                    small = src.resize((sw, shh), Image.LANCZOS)
                    mask = Image.new("L", (sw, shh), 255)
                    md = ImageDraw.Draw(mask)
                    fe = 80
                    for q in range(fe):
                        a_ = int(255 * (q + 1) / (fe + 1))
                        md.rectangle([q, q, sw - 1 - q, shh - 1 - q], outline=a_)
                    fr = off_bg.copy()
                    fr.paste(small, (int(pl.get("x", 0) * W), int(pl.get("y", 0) * H)), mask)
                    vx, vy, vc = -pl.get("x", 0) / sc, -pl.get("y", 0) / sc, 1 / sc  # 표식 변환용
                elif has_off:
                    if off_bg is None:
                        off_bg = Image.fromarray(np.clip(board_background(
                            np.asarray(fr.convert("RGB")).astype(np.float32)), 0, 255).astype(np.uint8))
                    fr = apply_offset(fr.convert("RGB"), off[0], off[1], off_bg)
                if not static_view:
                    if not pl:
                        vx, vy, vc, _ = view_box(z, focus)
                    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    dr = ImageDraw.Draw(lay)
                    any_ov = False
                    for m in marks:
                        if t < m["t"]:
                            continue
                        p = ease_out((t - m["t"]) / m["m"].get("dur", 0.35))
                        if m["m"].get("screen"):
                            tr = m["strokes"]
                        else:
                            tr = [[(((x / W - vx) / vc + off[0]) * W, ((y / H - vy) / vc + off[1]) * H)
                                   for x, y in st] for st in m["strokes"]]
                        draw_partial(dr, tr, p, m["m"].get("width", 20) * W / 1080, color(m["m"].get("color", "red")))
                        any_ov = True
                    for c in cards:
                        if t >= c["t"]:
                            c["art"].paste(lay, t - c["t"])
                            any_ov = True
                    fr = fr.convert("RGB") if fr.mode != "RGB" else fr
                    if xf_n and k < xf_n and prev_base is not None:  # 앞 샷에서 디졸브
                        fr = Image.blend(prev_base, fr, (k + 1) / (xf_n + 1))
                    base_last = fr
                    rgb = fr.copy()
                    if any_ov:
                        rgb.paste(lay, (0, 0), lay)
                    for art, s_, e_ in sub_arts:
                        if s_ <= t < e_:
                            rgb.paste(art.im, (art.x, art.y), art.im)
                    if k == nf // 2:
                        review.append((sh["block"], rgb.copy()))
                    enc.stdin.write(rgb.tobytes())
                    continue
                # 완료된 마크·카드는 캐시층, 진행 중은 새로 그림
                done = tuple(i for i, m in enumerate(marks) if t >= m["t"] + m["m"].get("dur", 0.35)) + \
                    tuple(100 + i for i, c in enumerate(cards) if t >= c["t"] + 0.22)
                if done not in done_cache:
                    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    dr = ImageDraw.Draw(lay)
                    for i in done:
                        if i < 100:
                            m = marks[i]
                            draw_partial(dr, m["strokes"], 1.0, m["m"].get("width", 20) * W / 1080,
                                         color(m["m"].get("color", "red")))
                    for i in done:
                        if i >= 100:
                            cards[i - 100]["art"].paste(lay, 1.0)
                    done_cache = {done: lay}
                lay = done_cache[done]
                live = [m for i, m in enumerate(marks) if i not in done and t >= m["t"]]
                livec = [c for i, c in enumerate(cards) if 100 + i not in done and t >= c["t"]]
                if live or livec:
                    lay = lay.copy()
                    dr = ImageDraw.Draw(lay)
                    for m in live:
                        p = ease_out((t - m["t"]) / m["m"].get("dur", 0.35))
                        draw_partial(dr, m["strokes"], p, m["m"].get("width", 20) * W / 1080,
                                     color(m["m"].get("color", "red")))
                    for c in livec:
                        c["art"].paste(lay, t - c["t"])
                fr = fr.convert("RGB") if fr.mode != "RGB" else fr
                if xf_n and k < xf_n and prev_base is not None:  # 앞 샷에서 디졸브
                    fr = Image.blend(prev_base, fr, (k + 1) / (xf_n + 1))
                base_last = fr
                rgb = fr.copy()
                if done or live or livec:
                    rgb.paste(lay, (0, 0), lay)
                for art, s_, e_ in sub_arts:
                    if s_ <= t < e_:
                        rgb.paste(art.im, (art.x, art.y), art.im)
                if k == nf // 2:
                    review.append((sh["block"], rgb.copy()))
                enc.stdin.write(rgb.tobytes())
            prev_base = base_last
    finally:
        enc.stdin.close()
        enc.wait()
    if enc.returncode != 0:
        raise AsmError("영상 인코딩 실패")

    # 4) 오디오 버스
    n = int(round(total * SR))
    foley = np.zeros((n, 2), np.float32)
    for sh in shots:
        s = sh["s"]
        src = P(s["file"])
        if os.path.splitext(src)[1].lower() in IMG_EXT or not has_audio(src) or s.get("freeze_prev"):
            continue
        d = (sh["fb"] - sh["fa"]) / fps
        if s.get("clip_end"):
            d = min(d, (s["clip_end"] - s.get("start", 0.0)) / s.get("speed", 1.0))
        a = read_audio(src, d, s.get("start", 0.0), s.get("speed", 1.0))
        fade = min(len(a), int(0.02 * SR))
        if fade:
            a[:fade] *= np.linspace(0, 1, fade)[:, None]
            a[-fade:] *= np.linspace(1, 0, fade)[:, None]
        place(foley, a * db(s.get("foley_db", M.get("foley_db", -30))), sh["fa"] / fps)
    sfx = np.zeros((n, 2), np.float32)
    if M.get("sfx", True):
        for kind, ta, obj in events:
            if kind == "mark":
                strokes = 2 if obj["type"] == "x" else (3 if obj["type"] in ("arrow", "dim") else 1)
                place(sfx, sfx_marker(obj.get("dur", 0.35), strokes, int(ta * 1000)), ta)
            else:
                place(sfx, sfx_pop(), ta)
        sfx *= db(M.get("sfx_db", -24) + 6)
    narr = np.zeros((n, 2), np.float32)
    vo_target = M.get("voice_block_lufs", -18.0)
    for pb in plan:
        if pb["tv"]:
            li = measure_lufs(pb["tv"])
            g = db(vo_target - li) if li is not None and li > -70 else 1.0
            place(narr, read_audio(pb["tv"]) * g, pb["start"] + pb["lead"])
    narr_raw = os.path.join(work, "narr_raw.wav")
    write_wav(narr_raw, narr)
    narr_n = os.path.join(work, "narr.wav")
    if narr.any():
        loudnorm_two_pass(narr_raw, narr_n, M.get("target_lufs", -16))
        narr = read_audio(narr_n)[:n]
        if len(narr) < n:
            narr = np.vstack([narr, np.zeros((n - len(narr), 2), np.float32)])
    mix = narr + foley + sfx
    if M.get("bgm"):
        bg = read_audio(P(M["bgm"]))
        if len(bg):
            reps = int(math.ceil(n / len(bg)))
            bg = np.tile(bg, (reps, 1))[:n] * db(M.get("bgm_db", -30))
            # 내레이션 구간 덕킹 (-6dB, 부드럽게)
            env = np.abs(narr).mean(1)
            k = int(0.25 * SR)
            env = np.convolve(env, np.ones(k) / k, mode="same")
            duck = 1 - 0.5 * np.clip(env / (env.max() * 0.15 + 1e-9), 0, 1)
            fo = int(M.get("bgm_fade", 0.4) * SR)
            bg[-fo:] *= np.linspace(1, 0, fo)[:, None]
            mix += bg * duck[:, None]
    mix_raw = os.path.join(work, "mix_raw.wav")
    write_wav(mix_raw, mix / max(1.0, float(np.abs(mix).max())))
    mix_n = os.path.join(work, "mix.wav")
    loudnorm_two_pass(mix_raw, mix_n, M.get("target_lufs", -16), tp=-2.0)

    # 5) 합치기
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ff(["-i", vid, "-i", mix_n, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-af", "alimiter=limit=0.8:level=false", "-movflags", "+faststart", "-t", f"{total:.4f}", out], "합치기")

    # 6) 검토 시트
    if review:
        tw = 216
        th = int(tw * H / W)
        cols = 8
        rows = (len(review) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw, rows * (th + 22)), (25, 25, 25))
        d = ImageDraw.Draw(sheet)
        for i, (bn, im) in enumerate(review):
            x, y = (i % cols) * tw, (i // cols) * (th + 22)
            sheet.paste(im.resize((tw, th)), (x, y + 22))
            d.text((x + 4, y + 4), f"B{bn} #{i + 1}", fill=(255, 220, 0))
        sheet.save(os.path.splitext(out)[0] + "_review.jpg", quality=85)

    # 7) 계측
    vd, ad = probe_dur(out, "v:0"), probe_dur(out, "a:0")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", out, "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    li = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    lufs, tpk = (float(li[-1]) if li else None), (float(tp[-1]) if tp else None)
    if abs(vd - total) > 0.05:
        qc_fail.append(f"영상 길이 {vd:.3f} ≠ {total:.3f}")
    if abs(ad - total) > 0.08:
        qc_fail.append(f"오디오 길이 {ad:.3f} ≠ {total:.3f}")
    target = M.get("target_lufs", -16)
    if lufs is None or abs(lufs - target) > 1.0:
        qc_fail.append(f"라우드니스 {lufs} LUFS (목표 {target}±1)")
    if tpk is None or tpk > -1.0:
        qc_fail.append(f"트루피크 {tpk} dBFS (> -1)")
    timing = [{"block": pb["b"]["n"], "start": round(pb["start"], 2), "dur": round(pb["dur"], 2),
               "speech": round(pb["sp"], 2) if pb["sp"] else None} for pb in plan]
    rep = {"out": out, "total_s": round(total, 3), "video_s": round(vd, 3), "audio_s": round(ad, 3),
           "lufs": lufs, "true_peak": tpk, "blocks": timing, "shots": len(shots),
           "subs": len(subs), "marks": sum(len(s["marks"]) for s in shots),
           "cards": sum(len(s["cards"]) for s in shots), "warnings": warnings, "fail": qc_fail,
           "qc": "QC PASS" if not qc_fail else "QC FAIL"}
    with open(os.path.splitext(out)[0] + "_qc.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if not qc_fail else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AsmError as e:
        print(json.dumps({"qc": "QC FAIL", "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
