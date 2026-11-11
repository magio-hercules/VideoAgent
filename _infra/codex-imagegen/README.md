# Codex 이미지 생성 도구

이 문서는 `codex_imagegen.py`의 **설치 조건·사용법·동작·제약**을 소유한다.
무엇을 언제 몇 장 만드는지(프롬프트 규칙·파일명·검수)는 `craft/playbooks/gpt-image.md`.

Codex CLI의 내장 `image_gen`(ChatGPT 이미지 생성)을 한 번 호출해 그림을 만들고, 정해진 파일명으로 저장한다.
ChatGPT 계정 로그인을 쓰므로 API 키가 필요 없다. **ChatGPT 요금제 사용량을 쓰므로 생성 전에 장수를 알리고 대표 승인을 받는다.**

기준일: 2026-11-11 · 시험 확인: Codex 0.167(데스크톱 앱 동봉)에서 생성·참조 그림·한글 프롬프트 동작, 결과 941×1672 PNG, 장당 약 40~60초

## 조건

| 항목 | 기준 |
|---|---|
| Codex | 최근 버전. 도구가 아래 순서로 찾아 **가장 높은 버전**을 쓴다: `CODEX_BIN` 환경 변수 → Codex 데스크톱 앱에 들어 있는 CLI(`%LOCALAPPDATA%\OpenAI\Codex\bin\<해시>\codex.exe`) → PATH의 `codex` |
| 로그인 | Codex가 ChatGPT 계정으로 로그인돼 있어야 한다(`codex login status`). 로그인은 대표가 한다 |
| 기능 | `image_generation`. 실행할 때마다 `--enable image_generation`을 붙이므로 설정 파일은 바꾸지 않는다 |
| Python | 3.9 이상, 표준 라이브러리만 |

- 오래된 CLI(예: npm 0.112)는 현재 계정 기본 모델을 못 써서 "requires a newer version" 오류로 멈춘다. 그래서 버전이 가장 높은 후보를 고른다.
- CLI 설치·업데이트는 승인 사항이다(`AGENTS.md` §3). 이 도구는 설치하지 않는다.

## 사용법

작업 폴더 루트에서 실행한다.

```text
# 쓸 Codex와 기능 상태만 확인 (생성 안 함)
python _infra/codex-imagegen/codex_imagegen.py --check

# 명령·지시문만 확인 (생성 안 함)
python _infra/codex-imagegen/codex_imagegen.py --dry-run --prompt-file <프롬프트.txt> --out <저장.png>

# 생성: 대표 그림 한 장 (참조 그림 첨부)
python _infra/codex-imagegen/codex_imagegen.py \
  --prompt-file productions/<종류>/<작품>/05_제작/대표이미지/prompts/EP###_B01.txt \
  --ref productions/<종류>/<작품>/04_화면설계/<기준그림>.png \
  --out productions/<종류>/<작품>/05_제작/대표이미지/EP###_B01_representative.png

# 같은 프롬프트로 여러 장 (스타일 시안 등): _v01, _v02 … 로 저장
python _infra/codex-imagegen/codex_imagegen.py --prompt "<문장>" --count 3 --out <폴더>/<이름>.png
```

| 옵션 | 뜻 |
|---|---|
| `--prompt` / `--prompt-file` | 프롬프트(파일은 UTF-8). 긴 프롬프트는 파일로 |
| `--ref` | 참조 그림. 여러 번 쓸 수 있다. 화풍·색·반복 인물을 맞추는 데 쓴다 |
| `--out` | 저장할 `.png`. **이미 있으면 생성 전에 멈춘다**(덮어쓰지 않음) |
| `--count` | 1~4장. 2장 이상이면 `<이름>_v01.png` … |
| `--codex` / `--model` / `--timeout` | 실행 파일·모델·제한 시간(기본 장당 300초) 직접 지정 |

출력은 JSON 요약이다: `status`(ok·partial·failed·dry_run), `thread_id`, `saved[].file`·`source`·`size`, `seconds`, `errors`.
종료 코드: 0 성공, 1 그림 없음, 2 사용법·환경 오류.

## 동작

1. 빈 임시 폴더에서 `codex exec --enable image_generation -s read-only --json`을 실행하고, 프롬프트를 표준입력으로 넘긴다. 읽기 전용이라 Codex가 파일을 고치지 못한다.
2. 지시문은 "image_gen만 쓰고, 장수만큼 한 번씩, 실패해도 다시 시도하지 않음"으로 고정한다.
3. Codex는 그림을 `~/.codex/generated_images/<thread_id>/`에 저장한다(`CODEX_HOME`이 있으면 그 아래). 도구가 이벤트에서 `thread_id`를 읽어 그 폴더의 그림을 `--out`으로 **복사**한다. 원본은 그대로 남는다.
4. 실패하면 자동으로 다시 만들지 않는다. 오류 내용을 보고 대표와 정한다.

## 제약

- 출력 크기는 모델이 정한다(시험 결과 9:16 세로 941×1672). ComfyUI 입력용 768×1344는 6단계에서 따로 만든다.
- 생성물·프롬프트에는 비밀 값을 넣지 않는다. 작품 폴더와 그림은 Git 제외 대상이다.
- 시험: `python -m unittest discover -s _infra/codex-imagegen/tests` (Codex를 실행하지 않음)
