# VideoAgent — 1인 지식 쇼츠 채널을 위한 영상 제작 에이전트

주제 선정부터 팩트체크·대본·그림·클립 생성·나레이션·조립·검수·썸네일·업로드 정보·성과 회고까지,
얼굴 없는 나레이션 쇼츠 **한 편 전체를 운영자와 함께 지휘하는 에이전트**의 규칙·절차·도구 저장소입니다.
Claude(Claude Code·Claude 프로젝트)와 Codex가 같은 규칙(`AGENTS.md`)으로 일합니다.

---

## 1. 누구를 위한 에이전트이고, 어떤 업무를 대신하나

**대상:** 유튜브 쇼츠 채널을 혼자 운영하는 크리에이터. 지금은 "익숙한 말·음식·물건의 유래와 기원"을 다루는
한국어 지식 쇼츠 채널 운영자(저) 한 명이 실제로 쓰고 있습니다.

혼자서 한 편을 만들려면 기획자·리서처·작가·일러스트레이터·영상 편집자·QA·마케터 역할을 모두 해야 합니다.
이 에이전트는 그중 반복적이고 시간이 많이 드는 일을 맡고, **운영자는 결정만** 합니다.

| 단계 | 에이전트가 하는 일 | 운영자가 하는 일 |
|---|---|---|
| 1 주제 | 후보 5~10개 발굴, 중복 확인, 진입 이유(Core/Casual/New) 비교, 추천 | 주제 선택 |
| 2 조사 | 주장 단위 팩트체크(F01~), 출처 등급(A~E)·확신도 판정 | — |
| 3 대본 | 대본 작성·개작, 배점 평가, TTS용·자막용 원고 분리, 예상 길이 | 대본 승인 |
| 4 스타일 | 같은 장면을 3~5화풍으로 동시 생성해 비교 시트 제작 | 크레딧 승인 → 스타일 선택 |
| 5 패키지 | 블록별 대표 그림, 콘티·시나리오, 클립 프롬프트, 타임라인 | 크레딧 승인 → 그림 승인 |
| 6~7 생성 | 나레이션 한 테이크, 로컬 ComfyUI로 클립 생성·자동 QC·재시도 | 나레이션 크레딧 승인 |
| 8 편집·검수 | 자막·그래픽·BGM 조립, 음량·자막 누락 QC, **만들지 않은 평가자의 독립 채점** | 시사본 확인 |
| 9 납품 | 썸네일 4종·비교 시트, 업로드 메타(출처·AI 고지 포함), Drive 납품 | 썸네일·제목 선택 |
| 10 공개 | — (자동 게시하지 않음) | 직접 게시 |
| 11 회고 | 성과 기록, 다음 실험 1개 제안 | Studio 캡처 전달 |

**지키는 선:** 크레딧 사용·게시·삭제·설치는 항상 운영자 승인 후에만 합니다. 확인되지 않은 설은 단정하지 않고,
그림 안에 글자를 생성하지 않으며, 확인한 것만 "완료"라고 보고합니다.

---

## 2. 진행 상황

### 지금 되는 것

- **기획 0~5단계** — Claude 프로젝트 채팅에서 운영 중이며, 이 방식으로 실제 에피소드를 계속 만들고 있습니다.
- **유료 생성 연결** — 힉스필드 MCP로 GPT 이미지(스타일 시안·대표 그림·썸네일 바탕)와 Eleven v4 나레이션. 견적 → 승인 → 생성 절차(`docs/runbooks/paid-generation.md`).
- **로컬 클립 생성** — 운영자 PC의 ComfyUI(MiniMax H3 R2V SpeedX6·I2V 터보, Z-Image Turbo, ACE-Step 1.5)를 comfy-mcp로 제어. `jobgen.py`가 워크플로 사본에 값만 넣어 작업 JSON을 만듭니다.
- **조립·검사 도구** — `assemble.py`(Whisper 단어 시각 자막, 숫자 카드, 잉크 마크, 보드 톤 보정, 음량·길이 QC), `clip_qc.py`(컷 수·앞쪽 정지·색 이탈 + 접촉 시트), `bgm_synth.py`.
- **문서 라우터** — 요청 태그로 읽을 문서만 고르는 읽기 전용 선택기와 모의시험 25건(`_infra/doc-router/`).
- **공개 경계** — 비밀 값은 `.env`, 채널 정보는 `private/`(둘 다 Git 제외), 허용 목록 `.gitignore`, 커밋 전 검사(`_infra/public-check/`).

### 아직 안 되는 것

- **두 작업 공간의 자동 동기화** — 기획 기록은 Claude 프로젝트, 제작 기준·도구는 이 저장소에 있고 사람이 맞춥니다(`AGENTS.md` §10).
- **조립 도구 통합** — 편마다 조립 설정이 달라 편별 스크립트가 늘었습니다. 공용 `assemble.py` 하나로 합치는 일이 남았습니다.
- **클론만으로 재현** — 워크플로 JSON과 동봉 노드 코드, 폰트 파일은 배포 권리를 확인하지 못해 넣지 않았습니다. 받는 곳은 각 README에 있습니다. 작품 예시도 넣지 않았습니다.
- **`.env` 자동 읽기** — 지금은 코드가 아니라 에이전트가 `.env`를 읽어 생성 요청에 넣습니다. 스크립트에서 직접 읽는 부분은 아직 없습니다.
- **성과 자동 수집** — YouTube Studio를 읽지 못해 운영자가 캡처·CSV를 전달합니다.
- **어디서나 쓰는 웹 화면** — 지금은 채팅 중심입니다. 웹사이트로 확장할 계획입니다.
- **다른 언어판** — 진행 방식 미정.
- **게시 자동화** — 의도적으로 만들지 않습니다. 게시는 운영자가 직접 합니다.

---

## 3. 사용 방법

> **처음 받아서 쓰는 분은 [`docs/setup.md`](docs/setup.md)부터 보세요.** 에이전트 도구 → 환경 변수·비공개 값 →
> 외부 서비스 연결 → 조립 도구 → 로컬 ComfyUI 순서로, 단계마다 무엇이 가능해지는지와 확인 방법을 적었습니다.
> 저장소에 넣지 않은 것(워크플로 JSON·폰트·모델)을 받는 곳도 거기에 있습니다.

### 3.1 준비물

| 구분 | 필요한 것 |
|---|---|
| 에이전트 | Claude Code 또는 Codex (이 폴더를 열면 `AGENTS.md`를 먼저 읽음). 기획은 Claude 프로젝트 채팅에서도 가능 |
| 커넥터 | 힉스필드 MCP(이미지·나레이션), Google Drive(에피소드 저장소). 둘 다 **로그인 방식**이라 키 파일이 필요 없음 |
| 로컬 생성 | Windows + NVIDIA GPU(12GB에서 검증), ComfyUI + comfy-mcp, 각 워크플로 README의 모델·노드 |
| 도구 | Python 3.10+, ffmpeg/ffprobe, `python -m pip install -r requirements.txt` (numpy, Pillow, 선택 faster-whisper) |

### 3.2 환경 변수 (`.env`)

비밀 값은 루트의 `.env`에만 둡니다. Git에 올라가지 않습니다.

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

| 변수 | 필요 | 넣을 값 | 얻는 곳 |
|---|---|---|---|
| `NARRATION_VOICE_NAME` | 나레이션을 만들 때 | 나레이션에 쓸 보이스 이름 | 힉스필드의 보이스 목록 (본인 보이스나 사용 허락을 받은 보이스만) |
| `NARRATION_VOICE_ELEMENT_ID` | 나레이션을 만들 때 | 위 보이스의 힉스필드 element ID | 같은 목록의 ID |
| `ELEVENLABS_VOICE_ID` | 선택 | ElevenLabs를 직접 쓸 때 보이스 ID | ElevenLabs Voice Library |
| `ELEVENLABS_API_KEY` | 선택 | ElevenLabs를 직접 쓸 때 API 키 | ElevenLabs 설정 → API Keys |
| `HIGGSFIELD_API_KEY` | 선택 | 커넥터 대신 API로 직접 호출할 때 | 힉스필드 계정 설정 |

- 에이전트는 값을 생성 요청에만 쓰고 문서·로그에 출력하지 않습니다.
- `.env`에 넣은 값(6자 이상)은 공개 검사가 자동으로 금지 문자열로 씁니다. 실수로 문서에 복사되면 커밋이 막힙니다.
- 키가 공개된 것 같으면 커밋을 지우는 데서 끝내지 말고 **즉시 재발급**합니다.

### 3.3 비공개 값 (`private/`)

채널 고유 정보는 `private/`에 둡니다. 이 폴더는 안내문 `private/README.md`만 공개되고 나머지는 Git에서 빠집니다.

```bash
cp config/channel.example.md private/channel.md
```

| 파일 | 필요 | 들어갈 값 |
|---|---|---|
| `private/channel.md` | 권장 | 채널 이름·핸들, 한 줄 소개, 형식·길이·주기, 타깃, 목표 우선순위, 소재 범위, 성과 지표 우선순위, 썸네일 문구 패턴, 금지 고정 멘트, 에피소드 저장소 루트 이름 |
| `private/decisions.md` | 권장 | 운영자 결정 기록 (날짜 / 결정 / 반영 위치) — 공개 문서보다 우선 |
| `private/episode-index.md` | 권장 | 회차 목록 (회차 / 소재 / 작업 코드 / 납품물 / 상태 / 공개일·URL) |
| `private/analytics.md` | 선택 | 성과 분석 방법 (지표 정의·수집 항목·회고·실험 설계·수익화 조건) |
| `private/denylist.txt` | **공개 전 필수** | 공개되면 안 되는 문자열을 한 줄에 하나씩 (채널명·핸들·보이스 이름·회사명·개인 아이디 등) |

양식과 예시는 `private/README.md`에 있습니다. `private/channel.md`가 없으면 에이전트는 `config/channel.example.md`를 기본값으로 씁니다.

### 3.4 설치 확인

```bash
git config core.hooksPath .githooks                    # 커밋 전 공개 검사 훅
python _infra/doc-router/router.py --check             # 문서 구조 검사
python -m unittest discover -s _infra/doc-router/tests # 라우터 모의시험
python _infra/public-check/check_public.py             # 공개 검사 (커밋·Push 전)
```

Windows에서 `python`이 없으면 `py`를 씁니다.

### 3.5 요청 예

에이전트에게 아래처럼 말하면 해당 단계부터 진행합니다(전체 목록: `craft/doctrine/production-cycle.md` §5).

| 요청 | 하는 일 |
|---|---|
| "새 편 주제 추천해줘" | 1단계: 후보 비교와 추천 |
| "<주제> 정적 패키지까지" | 1~5단계: 대본·대표 그림·콘티·프롬프트까지 만들고 멈춤 |
| "<주제> 알아서 끝까지" | 1~9단계: 승인 항목만 묻고 끝까지 |
| "이어서: EP###" | 그 편의 `생성상태.md`부터 이어서 |
| "에이전트 점검" | PC 연결·ComfyUI·디스크·커넥터 점검 |

에이전트가 문서를 고르는 방법:

```bash
python _infra/doc-router/router.py --tags "기획 쇼츠"
python _infra/doc-router/router.py --tags "재개" --path "productions/shorts/EP030_소재"
```

---

## 4. 구조

```text
기획 작업 공간 (Claude 프로젝트)          운영자 PC (이 저장소)
 ├ 프로젝트 문서: 결정·회차·편별 기록      ├ AGENTS.md / CLAUDE.md     공통 규칙·진입
 ├ 웹 검색 (팩트체크)                    ├ craft/doctrine/            단계·기획·제작 표준·팩트체크
 ├ Google Drive 커넥터 (에피소드 정본)   ├ craft/playbooks/           모델별 문법과 실패 대응
 └ 힉스필드 MCP (GPT 이미지·나레이션)     ├ docs/runbooks/             점검·실행·전송·검수·납품 절차
                │                        ├ docs/agent/ + _infra/doc-router/   문서 라우터
                └──── 데스크톱 앱 ────────┤ library/                     프롬프트 골격·워크플로 설정
                      (PC 셸·파일 전송)   ├ _infra/shorts-tools/       jobgen·assemble·clip_qc·bgm_synth
                                          ├ _infra/public-check/       공개 검사
                                          ├ productions/_template/     작품 양식 (작품 폴더는 비공개)
                                          ├ config/ · private/README.md   설정 양식과 비공개 폴더 안내
                                          └ ComfyUI ← comfy-mcp         클립·정지 컷·BGM 생성
```

자세한 지도는 `INDEX.md`, 문서 소유권과 라우트는 `docs/agent/README.md`.

---

## 5. 보안·공개 원칙

- API 키·토큰·보이스 ID는 `.env`에만 둡니다. 문서와 코드에는 변수 이름만 씁니다.
- 채널 이름·운영 결정·회차·성과·편별 기록은 `private/`에만 둡니다.
- `.gitignore`는 허용 목록 방식입니다. 공개할 경로만 열고, 미디어·모델·폰트·압축 파일은 어디서든 막습니다.
- `check_public.py`가 키 모양 문자열, 개인 절대경로, 이메일, `private/denylist.txt`의 문자열, `.env` 값을 찾으면 커밋을 막습니다. 찾은 값은 화면에 출력하지 않습니다.
- `git add -f`나 `--no-verify`로 제외 규칙·검사를 우회하지 않습니다.
