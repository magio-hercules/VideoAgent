# 에피소드 기계용 상태

이 문서는 작품 `생성상태.md` 맨 위 **기계용 상태 블록의 형식과 필드 뜻**을 소유한다.
누가 언제 상태를 바꾸는지(작업 분담·인계 규칙)는 `craft/doctrine/production-cycle.md` §1.

Codex(ChatGPT)·Claude·웹 화면이 같은 블록을 읽고 고쳐서, 어느 쪽에서 이어받든 지금 단계와 담당을 바로 안다.
사람이 읽는 기록(대표 선택 기록, 채택판, 메모)은 같은 파일 아래쪽에 그대로 둔다.

## 형식

`생성상태.md`의 `## 기계용 상태` 절에 아래 코드 블록 **하나만** 둔다. 정보 문자열은 정확히 `json videoagent-state`.

````markdown
```json videoagent-state
{
  "schema": "videoagent.episode-state/1",
  "episode": "EP031",
  "topic": "소재 한 줄",
  "stage": 5,
  "status": "handoff_ready",
  "assignee": "claude",
  "handoff": {"status": "ready", "at": "2026-11-11T10:00+09:00", "note": "B04 손 모양 재확인 필요"},
  "versions": {"script": "v03", "style": "S2", "representative": "v1", "timeline": "가안", "meta": null, "video": null},
  "block_count": 9,
  "next_action": "6단계: 나레이션 견적 → 승인 → 생성",
  "pending_operator": [],
  "updated_at": "2026-11-11T10:00+09:00",
  "updated_by": "chatgpt"
}
```
````

## 필드

| 필드 | 값 | 뜻 |
|---|---|---|
| `schema` | `videoagent.episode-state/1` | 형식 버전 |
| `episode` | `EP###` | 회차 코드 (`private/episode-index.md`의 번호) |
| `topic` | 문자열 | 소재 한 줄 |
| `stage` | 0~11 | 지금 단계 (`production-cycle.md` §2 단계표) |
| `status` | 아래 표 | 지금 상태 |
| `assignee` | `chatgpt` · `claude` · `operator` | 다음에 움직일 쪽 |
| `handoff.status` | `none` · `ready` · `accepted` · `returned` | ChatGPT → Claude 인계 상태 |
| `handoff.at` | ISO 시각 또는 `null` | 마지막 인계 상태 변경 시각 |
| `handoff.note` | 문자열 | 인계 메모 (받는 쪽이 먼저 볼 것, 되돌린 이유) |
| `versions.*` | 문자열 또는 `null` | 지금 쓰는 버전: `script`·`style`·`representative`·`timeline`·`meta`·`video` |
| `block_count` | 정수 또는 `null` | 블록 수 (4단계에서 정함). 인계 검사가 대표 그림 수를 맞춰 본다 |
| `next_action` | 문자열 | 다음 행동 한 줄 |
| `pending_operator` | 배열 (문자열 또는 결정 카드 객체) | 대표 확인·승인 대기 항목. 아래 결정 카드 참고 |
| `updated_at` | 시간대 붙은 ISO 시각 | 마지막 갱신 (KST `+09:00`) |
| `updated_by` | `chatgpt` · `claude` · `operator` · `web` | 마지막으로 고친 쪽 |
| `stage_log` (선택) | `[{stage, started_at, ended_at, note}]` | 단계 이력. 단계가 바뀔 때 앞 항목의 `ended_at`을 채우고 새 항목을 붙인다. 시각은 시간대 붙은 ISO, 정확한 시각을 모르면 날짜(`YYYY-MM-DD`)만. 진행 중이면 `ended_at: null` |

| `status` | 뜻 |
|---|---|
| `active` | 담당이 작업 중 |
| `waiting_operator` | 대표의 선택·승인 대기 (`pending_operator`에 항목 필수) |
| `waiting_pc` | 6단계 이후인데 PC·ComfyUI를 쓸 수 없어 멈춤 (담당 `claude`) |
| `handoff_ready` | 5단계까지 끝나 Claude가 받을 수 있음 (`handoff.status=ready`, `stage=5`, 담당 `claude`) |
| `on_hold` | 대표가 보류 |
| `done` | 공개·회고까지 끝남 |

### 결정 카드 (`pending_operator` 항목)

간단한 확인은 문자열 한 줄로 쓴다. 대표가 고르거나 승인할 것은 객체로 쓰면 제작 보드에서 버튼 한 번으로 답할 수 있다.

```json
{"id": "thumb", "question": "썸네일과 제목을 골라 주세요", "kind": "choose",
 "options": ["T1", "T2", "T3"], "recommend": "T2", "note": "T2가 대비가 가장 크다", "refs": ["07_게시준비/thumb_sheet.png"]}
```

| 필드 | 값 | 뜻 |
|---|---|---|
| `question` | 문자열 (필수) | 대표에게 묻는 말 |
| `kind` | `approve` 승인 · `choose` 고르기 · `confirm` 했는지 확인 · `cost` 비용 승인 · `info` 정보 입력 | 보드가 보여 줄 버튼 (기본 `info`) |
| `options` | 문자열 배열 | 고를 것. `choose`면 2개 이상 |
| `recommend` | `options` 중 하나 | 에이전트 추천안 |
| `id` | 영문·숫자·`_-` 40자 이하 | 보드 요청이 이 항목을 가리키는 이름. 없으면 동기화 도구가 질문 글로 만든다 |
| `note`, `refs` | 문자열, 문자열 배열 | 추천 근거 한 줄, 근거 파일(작품 폴더 기준 경로) |

- `cost`는 비용이 드는 일이다. `note`에 견적과 범위(금액·장수·대상)를 적는다. 보드 승인은 대표의 명시적 승인이므로 그 범위 안에서는 다시 묻지 않고 실행한다. 범위를 넘으면 새 카드로 묻는다(운영 결정 2026-11-15).

## 지킬 것

- 블록은 파일당 하나. 값을 바꾸면 `updated_at`·`updated_by`도 함께 바꾼다.
- 상태 블록에는 비밀 값·개인 경로를 넣지 않는다.
- 블록과 사람용 기록이 다르면 블록을 고치고, 사람용 기록에 이유를 한 줄 남긴다.

## 검사

```text
python _infra/episode-state/episode_state.py check productions/<종류>/<작품>            # 형식·일관성
python _infra/episode-state/episode_state.py check productions/<종류>/<작품> --handoff  # + 인계 체크리스트
python _infra/episode-state/episode_state.py list [--json]                               # 전체 작품 상태
python -m unittest discover -s _infra/episode-state/tests
```

`--handoff`(또는 `handoff.status=ready`)이면 대본·스타일·대표 그림 버전, `block_count`, `BRIEF.md`,
블록마다 `<EP>_Bxx_representative.png`가 작품 폴더 안에 있는지 확인한다. 그림의 내용 검수는 사람·에이전트가 한다.
`list --json` 출력은 웹 화면 동기화에 그대로 쓴다(→ `docs/design/web-console.md`).
