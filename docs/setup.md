# 설치·설정 안내 — 이 저장소를 받아서 쓰는 사람을 위한 문서

이 문서는 저장소를 처음 받은 사람이 **에이전트를 동작시키기까지 설정할 것**을 소유한다.
무엇을 하는 에이전트인지는 `README.md`, 작업 규칙은 `AGENTS.md`.

저장소에는 규칙·절차·도구만 들어 있다. 아래는 **각자 준비해야 하는 것**이다. 단계마다 무엇이 가능해지는지 적었으니,
필요한 만큼만 진행하면 된다(예: 기획만 쓸 거라면 1~3단계).

| 단계 | 준비할 것 | 이걸 하면 되는 일 |
|---|---|---|
| 1 | 에이전트 도구, Python | 문서 라우터, 기획·대본·팩트체크(0~3단계) |
| 2 | `.env`, `private/` | 내 채널 기준으로 동작, 공개 검사 |
| 3 | 힉스필드·Google Drive 연결 | 스타일 시안·대표 그림·나레이션(4~6단계), 에피소드 저장 |
| 4 | ffmpeg, 파이썬 패키지, 폰트 | 클립 검사·조립·배경음악 합성(8단계) |
| 5 | ComfyUI, 모델, 워크플로 JSON, comfy-mcp | 로컬 클립 생성(7단계) |

---

## 1. 에이전트 도구와 Python

- **에이전트:** Claude Code 또는 Codex. 저장소 폴더를 열면 `AGENTS.md`(Claude는 `CLAUDE.md` → `AGENTS.md`)를 먼저 읽는다.
- **Python 3.10 이상.** Windows에서 `python`이 없으면 `py`를 쓴다.

```bash
git clone https://github.com/<계정>/<저장소>.git
cd <저장소>
python _infra/doc-router/router.py --check
python -m unittest discover -s _infra/doc-router/tests
```

두 명령이 통과하면 에이전트가 요청에 맞는 문서를 고를 수 있다.

### 실행 환경에 따라 다른 점

런북(`docs/runbooks/`)은 **Claude 앱의 클라우드 세션이 데스크톱 앱을 통해 PC를 다루는 방식**으로 쓰여 있다.
PC에서 Claude Code·Codex를 직접 실행하면 아래처럼 바꿔 읽는다.

| 런북 표현 | PC에서 직접 실행할 때 |
|---|---|
| `device_bash`에서 실행 | 그 PC의 터미널에서 실행 |
| `device_stage_files` / `device_commit_files` (클라우드 ↔ PC 전송) | 필요 없음. 파일이 이미 같은 PC에 있다 |
| "PC 셸은 한 번에 최대 3분" 제약 | 해당 없음. 긴 렌더(조립)도 PC에서 돌려도 된다 |
| `get_device_info`의 `connectedFolders` | 저장소 폴더의 실제 경로 |

---

## 2. 비밀 값과 채널 설정

```bash
cp .env.example .env                              # Windows: copy .env.example .env
cp config/channel.example.md private/channel.md   # Windows: copy config\channel.example.md private\channel.md
git config core.hooksPath .githooks               # 커밋 전 공개 검사 훅
```

- **`.env`:** 변수별 의미와 얻는 곳은 `README.md` §3.2. 지금 쓰는 연결은 모두 로그인 방식이라 키가 없어도 기획 단계는 동작한다. 나레이션을 만들려면 보이스 값 두 개가 필요하다.
- **`private/`:** 넣을 파일과 양식은 `private/README.md`. 최소한 `channel.md`를 채우고, 저장소를 공개할 거라면 `denylist.txt`도 만든다.
- 둘 다 Git에 올라가지 않는다. 확인: `python _infra/public-check/check_public.py --list`에 `.env`와 `private/README.md` 말고 다른 `private/` 파일이 없어야 한다.

---

## 3. 외부 서비스 연결 (유료 생성·에피소드 저장)

| 서비스 | 용도 | 연결 방법 | 비용 |
|---|---|---|---|
| 힉스필드 (Higgsfield) MCP | GPT 이미지(`gpt_image_2_6`), 나레이션(`elevenlabs_v4`) | Claude 앱이면 커넥터에서 로그인. Claude Code·Codex면 각 도구의 MCP 서버 설정에 힉스필드 MCP를 추가 | 크레딧. 생성마다 에이전트가 견적을 먼저 보이고 승인을 받는다 |
| Google Drive | 에피소드 정본 저장소 (편별 폴더) | Claude 앱이면 커넥터에서 로그인. 대신 Drive 데스크톱의 동기화 폴더를 써도 된다 | 무료 |

- 저장소 루트 폴더 이름(예: `MyChannel/`)을 `private/channel.md`의 "에피소드 저장소 루트"에 적는다. 하위 폴더 구조는 `docs/runbooks/local-generation.md` §3.
- 나레이션 보이스는 **본인 목소리이거나 사용 허락을 받은 것**만 쓴다(`craft/doctrine/factcheck-rights.md` §5). 보이스 이름·ID를 `.env`에 넣는다.
- 다른 이미지·음성 서비스를 쓰려면 `docs/runbooks/paid-generation.md`의 서비스 표와 해당 플레이북을 바꾼다.

---

## 4. 조립·검사 도구

```bash
python -m pip install -r requirements.txt   # numpy, Pillow, (선택) faster-whisper
ffmpeg -version                             # ffmpeg·ffprobe가 PATH에 있어야 한다
```

- **폰트:** 파일은 저장소에 없다. `_infra/shorts-tools/fonts/README.md`의 받는 곳에서 받아 같은 폴더에 두고, 조립 매니페스트의 `font`·`card_font`에 그 경로를 적는다.
- **Whisper:** faster-whisper는 처음 실행할 때 모델을 내려받는다(네트워크 필요). 없으면 자막 단어 시각 단계(`assemble.py --words-only`)를 설치된 기계에서 따로 돌린다.
- 확인: `python _infra/shorts-tools/clip_qc.py <아무 mp4>`가 시트 이미지를 만들면 된다.

---

## 5. 로컬 클립 생성 (ComfyUI)

검증한 환경은 Windows 11 + NVIDIA RTX 5070 12GB다. 다른 GPU에서는 길이·해상도 상한을 다시 잰다(`docs/runbooks/local-generation.md` §5).

1. **ComfyUI 설치.** 기동·업데이트 방법은 ComfyUI 안내를 따른다.
2. **워크플로 JSON 받기.** 배포 권리를 확인하지 못해 저장소에 넣지 않았다. 각 README의 "받는 곳"을 따라 받아 `original/`에 둔다.
   - `library/workflows/h3-r2v-speedx6/README.md` — 원본 워크플로를 받은 뒤, 같은 README의 "원본 대비 변경" 표대로 쇼츠용 사본 `shorts_r2v_9x16.json`을 만든다(`jobgen.py`가 이 파일을 읽는다).
   - `library/workflows/still-zimage-turbo/README.md` — ComfyUI 공식 템플릿 `image_z_image_turbo`.
3. **모델·커스텀 노드 설치.** 필요한 파일과 노드 목록은 각 워크플로 README의 "의존성 상태"·"구성" 절이 소유한다. MiniMax H3는 라이선스에 제외 지역이 있으니 쓰기 전에 본인 지역을 확인한다.
4. **comfy-mcp 연결.** 에이전트가 ComfyUI를 다루는 MCP 서버다. 쓰는 에이전트 도구(Claude 데스크톱 앱, Claude Code, Codex)의 MCP 설정에 등록한다. 확인: 에이전트에게 "에이전트 점검"을 시키면 `server_info`로 서버 상태와 입력·출력 폴더를 보고한다.
5. **디스크 여유 30GB 이상**을 확보한다. 모자라면 엉뚱한 오류로 실패한다.

---

## 6. 첫 실행 확인

에이전트에게 차례로 요청한다.

1. "에이전트 점검" — 연결·서버·디스크 상태 보고 (`docs/runbooks/local-generation.md` §1)
2. "새 편 주제 추천해줘" — 후보 비교표가 나오면 기획 단계가 동작한다
3. "<주제> 정적 패키지까지" — 크레딧 견적을 묻는 단계까지 오면 유료 생성 연결이 된 것이다

막히면 에이전트가 "미확인" 항목과 필요한 입력을 보고한다. 실행 중에 생기는 작품 폴더(`productions/<종류>/<작품>/`)는 Git에 올라가지 않는다.
