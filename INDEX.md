# INDEX — 폴더 지도 (사람용)

이 문서는 폴더 구조를 한눈에 보여주는 지도일 뿐이다. 작품 상태나 작업 이력을
소유하지 않으며 기본 라우트에도 포함되지 않는다. "공개"는 Git 저장소에 올라가는지 여부다.

| 경로 | 역할 | 공개 |
|---|---|---|
| `README.md` | 저장소 소개: 대상·업무·진행 상황·사용법 | 공개 |
| `docs/setup.md` | 처음 받은 사람을 위한 설치·설정 안내 | 공개 |
| `requirements.txt` | 공용 도구의 파이썬 의존성 | 공개 |
| `AGENTS.md` | 모든 작업 공통의 안전·권위·보존·공개 경계·라우팅 규칙 | 공개 |
| `CLAUDE.md` | Claude용 진입 연결문 (AGENTS.md를 가리킴) | 공개 |
| `.agent-system.json` | 문서 시스템 버전 표식과 관리 파일 기준 해시 | 공개 |
| `.gitignore` · `.githooks/` | 허용 목록 제외 규칙, 커밋 전 공개 검사 훅 | 공개 |
| `.env.example` / `.env` | 비밀 값의 변수 이름 / 실제 값 | 공개 / **비공개** |
| `config/` | 채널 설정 양식(`channel.example.md`) | 공개 |
| `private/README.md` | 비공개 폴더에 넣을 파일과 양식 안내 | 공개 |
| `private/` 나머지 | 채널 설정·운영자 결정·회차 목록·성과 분석 방법·금지 문자열 | **비공개** |
| `docs/agent/` | 문서 라우터: 소유권 표, 라우트 표, routes.json, 스키마 | 공개 |
| `docs/runbooks/` | 점검·실행·전송·복구, 유료 생성, 검수·조립·납품 | 공개 |
| `craft/doctrine/` | 단계·기획·제작 표준·팩트체크 | 공개 |
| `craft/playbooks/` | 모델·작업별 문법과 반복 실패 대응 | 공개 |
| `library/prompts/` | 재사용 프롬프트 골격과 모델 색인 | 공개 |
| `library/workflows/` | 워크플로 설정 README (JSON·동봉 코드는 비공개) | README만 |
| `productions/_template/` | 새 작품 양식: BRIEF·생성상태·renders | 공개 |
| `productions/<종류>/<작품>/` | 작품별 기획·기록·생성물 | **비공개** |
| `_infra/doc-router/` | 읽기 전용 문서 라우터와 테스트 | 공개 |
| `_infra/shorts-tools/` | jobgen·assemble·clip_qc·bgm_synth (폰트 파일은 비공개) | 공개 |
| `_infra/public-check/` | 공개 검사 스크립트 | 공개 |
| `_scratch/` | 임시·실험 파일 | **비공개** |
