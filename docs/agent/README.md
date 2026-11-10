# 문서 라우터 안내

라우터는 현재 요청에 필요한 문서만 고르는 **읽기 전용 선택기**다. 행동을 실행하지
않으며, 고른 문서가 설치·삭제·비용·업로드 권한을 늘리지도 않는다.

## 사용법

```text
python _infra/doc-router/router.py --tags "프롬프트" --path "productions/shorts/작품명"
python _infra/doc-router/router.py --tags "재개" --path "productions/shorts/작품명" --json
python _infra/doc-router/router.py --check
python -m unittest discover -s _infra/doc-router/tests
```

- 태그는 쉼표나 공백으로 여러 개 줄 수 있다. 라우트 ID를 그대로 써도 된다.
- `쇼츠`, `h3`, `r2v`, `i2v`, `zimage`, `gpt`, `대표그림`, `나레이션`, `권리`, `판정` 등은 **보조 태그**다. 라우트를 고르지 않고, 함께 준 라우트에 문서만 더한다(예: `--tags "프롬프트 h3 쇼츠"`).
- `--path`는 작업 폴더 기준 슬래시 상대경로만 받는다. 절대경로, `..`, 작업 폴더 밖으로 향하는 링크는 거부한다.
- Python이 없으면 설치하지 말고 아래 표를 수동으로 따른다.
- `private/`는 Git 밖에 있어 라우트에 넣지 않는다. 예외로 공개되는 안내문 `private/README.md`만 라우트에 넣고, 그 문서가 비공개 파일을 가리킨다.

## 라우트 표 (수동 진입용)

| 라우트 | 요청 예 | 대표 태그 | 기본 문서 | 조건부 문서 |
|---|---|---|---|---|
| repo-docs | 문서 구조를 고쳐 | 문서구조, docs | docs/agent/README.md | +라우터 → routes.json, routes.schema.json |
| story-planning | 새 편 주제·대본을 정하자 | 기획, 주제, 대본, 팩트체크, 조사 | craft/doctrine/production-cycle.md, craft/doctrine/planning.md | +쇼츠 → shorts-format.md · +팩트체크/조사/권리 → factcheck-rights.md · 작품 경로 → 가까운 BRIEF.md |
| prompt-writing | 콘티·클립 프롬프트만 작성해 | 프롬프트, 콘티 | library/prompts/README.md | +모델문법 → playbooks/README.md · +h3/r2v → minimax-h3-r2v.md, r2v-block-skeleton.md · +i2v → minimax-h3-i2v-turbo.md · +zimage → z-image-turbo.md · +gpt/대표그림 → gpt-image.md · +쇼츠 → shorts-format.md · 작품 경로 → BRIEF.md |
| local-run | 로컬에서 실행해 / 에이전트 점검 | 로컬실행, comfyui, 점검 | docs/runbooks/local-generation.md | +워크플로/comfyui → workflows/README.md · +h3/r2v → h3-r2v-speedx6/README.md · +i2v → minimax-h3-i2v-turbo.md · +zimage → still-zimage-turbo/README.md · 작품 경로 → 생성상태.md |
| paid-generation | 대표 그림·나레이션을 만들어 | 유료생성, 크레딧 | docs/runbooks/paid-generation.md | +gpt/대표그림 → gpt-image.md · +나레이션 → post-production.md · 작품 경로 → 생성상태.md |
| resume-project | 이 작품 이어서 하자 | 재개, 이어서 | (없음) | 지목한 작품의 가까운 생성상태.md → BRIEF.md |
| review-delivery | 조립·검수·썸네일·납품 | 검수, 조립, 편집, 썸네일, 메타, 납품 | docs/runbooks/review-delivery.md | +조립/나레이션/자막 → post-production.md · +쇼츠/썸네일/메타/판정 → shorts-format.md · 작품 경로 → renders.md → 생성상태.md |
| performance | 성과 기록·회고 | 성과, 회고 | private/README.md (→ 비공개 `private/analytics.md`를 이어서 읽음) | 작품 경로 → 가까운 renders.md |

정확한 정의는 `docs/agent/routes.json`이 소유한다. 이 표와 다르면 routes.json이 정본이다.

## 기본으로 읽지 않는 문서

루트 `CONTEXT.md`, 루트 `renders.md`, 전체 `logs/`. 필요하면 사용자가 지목했을 때만 읽는다.

## 문서 소유권 표

| 정보 | 단일 소유자 |
|---|---|
| 모든 작업에 필요한 안전·권위·보존·공개 경계·라우팅 | `AGENTS.md` |
| 처음 받은 사람의 설치·설정 | `docs/setup.md` |
| 한 편의 단계·승인 지점·납품 기준 | `craft/doctrine/production-cycle.md` |
| 0~6단계 실행 방법 | `craft/doctrine/planning.md` |
| 사양·연출·자막·소리·썸네일·메타·판정 기준 | `craft/doctrine/shorts-format.md` |
| 팩트체크·권리·정정 | `craft/doctrine/factcheck-rights.md` |
| 성과 지표·회고·실험 방법 (비공개) | `private/analytics.md` |
| 모델·작업별 문법과 반복 실패 대응 | `craft/playbooks/{이름}.md` |
| 정확한 워크플로 설정 | `library/workflows/{워크플로}/README.md` |
| 프롬프트 파일 규칙과 모델 색인 | `library/prompts/README.md` |
| 점검·실행·전송·복구 절차 | `docs/runbooks/` |
| 작품의 기획 | `productions/{종류}/{작품}/BRIEF.md` |
| 현재 진행점·채택판·다음 행동 | `productions/{종류}/{작품}/생성상태.md` |
| 작품별 생성 결과·판정·성과 | `productions/{종류}/{작품}/renders.md` |
| 작업 종류별 읽기 순서 | `docs/agent/routes.json` |
| 채널 고유 값 (비공개) | `private/channel.md` (기본값: `config/channel.example.md`) |
| 운영자 결정 (비공개) | `private/decisions.md` |
| 회차 목록·상태 (비공개) | `private/episode-index.md` |
| 비밀 값 (비공개) | `.env` (변수 목록: `.env.example`) |
| private/ 폴더 안내 (공개) | `private/README.md` |

## 라우트를 바꿀 때

1. `routes.json`을 고친다 (스키마: `routes.schema.json`).
2. `--check`를 실행한다.
3. 테스트(대표 요청 모의시험)를 실행한다.
4. 이 문서의 라우트 표를 맞춘다.
