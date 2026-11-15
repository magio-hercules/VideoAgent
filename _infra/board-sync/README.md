# 제작 보드 동기화 도구

이 문서는 제작 보드 **페이지 파일과 동기화 도구의 사용법**을 소유한다.
보드의 목적·데이터 구조·동기화 규칙·요청 처리 규칙은 `docs/design/web-console.md`.

| 파일 | 내용 |
|---|---|
| `board.html` | 보드 페이지(claude.ai 아티팩트). 진행(대표 확인 대기·단계 지도·진행 카드), 이력, 요청·활동 보기. 데이터는 페이지에 넣지 않고 아티팩트 DB에서 읽는다. DB에 닿지 않으면(claude.ai 밖·로그인 안 함·`db` 미선언) 가상의 견본 회차로 **체험 모드**를 보여 주고, 요청 버튼은 화면 안에서만 흉내 낸다 |
| `board_sync.py` | 상태 블록 + 회차 목록 사본(`private/episode-index.md`)으로 `episodes` 문서 JSON을, 각 편 `BRIEF.md`로 단계별 결과물 `outputs` 문서 JSON을 만든다. 파일만 쓰고 보드에는 쓰지 않는다 |
| `tests/` | `python -m unittest discover -s _infra/board-sync/tests` |

보드 주소는 채널 정보와 같이 다루어 `private/channel.md`의 "제작 보드"에만 적는다.

## 동기화 (에이전트가 할 일)

실행 순서 전체는 스킬 `/board`(`.claude/skills/board/SKILL.md`). 도구 부분만:

```text
python _infra/board-sync/board_sync.py build --out <에이전트 스크래치>/board-sync   # 바뀐 문서만 batch.json에
python _infra/board-sync/board_sync.py commit --out <같은 폴더>                      # 보드에 쓴 뒤
```

- `build`는 문서마다 내용 지문(`content_hash`)을 붙이고, 지난 `commit` 기준과 다른 문서만 `batch.json`에 담는다. `meta/sync`는 늘 담고, 바뀐 문서가 있으면 `log`도 한 건 담는다. `--all`은 전부 담는다.
- `batch.json` 항목은 `{op, collection, doc_id, file_path}`. 이미 있는 문서에는 쓰기 전에 읽은 `version`을 `if_version`으로 붙인다.
- 상태 블록의 `pending_operator`는 보드용 결정 카드 객체(`id`·`question`·`kind`·`options`·`recommend`…)로 맞춰진다. 문자열 항목의 `id`는 질문 글로 만든 고정값이다.
- `outputs`는 `BRIEF.md`를 `## N.` 절 단위로 나눈 것이다. `productions/_template/BRIEF.md`와 똑같은 문단·코드 블록·표 행(아직 안 채운 칸)은 뺀다. 문서가 20만 자를 넘으면 원본 위치만 적는다.
- 그림: `build`가 공개 전 편의 단계별 그림 중 새로 생기거나 바뀐 것을 `media_upload.json`에 담는다. 에이전트가 보드 자산으로 올린 뒤 `media-batch --map <대응표>`로 `media` 문서 쓰기 묶음(`media_batch.json`)을 만든다. 대응표는 `{파일 경로: 자산 id}` 또는 `{파일 경로: {"asset": id, "caption": 설명}}`.
- 원본에서 사라진 문서(결과물 포함)는 지우지 않고 알리기만 한다. 보드에서 지울지는 대표에게 확인한다.
- 출력 폴더는 저장소 밖(또는 `_scratch/`)만 허용한다. 회차 목록은 채널 정보라 Git에 남기지 않는다.

## 페이지 다시 배포

`board.html`을 고친 뒤 같은 아티팩트 주소로 다시 배포한다(Artifact `url` = 보드 주소, capabilities `db`·`user`·`comments`). 데이터는 그대로 남는다.

체험판(심사·소개용 공개 주소)은 같은 `board.html`을 운영 보드와 **다른 아티팩트**로, capabilities 없이 배포한다.
`db`가 없으니 누가 열어도 체험 모드로만 열리고 실제 데이터는 보이지 않는다. 운영 보드에는 공개 링크를 켜지 않는다
(로그인한 외부인이 DB를 읽을 수 있다). 체험판 주소도 `private/channel.md`에 적는다.
