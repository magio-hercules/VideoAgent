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
| `pending_operator` | 문자열 배열 | 대표 확인·승인 대기 항목 |
| `updated_at` | 시간대 붙은 ISO 시각 | 마지막 갱신 (KST `+09:00`) |
| `updated_by` | `chatgpt` · `claude` · `operator` · `web` | 마지막으로 고친 쪽 |

| `status` | 뜻 |
|---|---|
| `active` | 담당이 작업 중 |
| `waiting_operator` | 대표의 선택·승인 대기 (`pending_operator`에 항목 필수) |
| `waiting_pc` | 6단계 이후인데 PC·ComfyUI를 쓸 수 없어 멈춤 (담당 `claude`) |
| `handoff_ready` | 5단계까지 끝나 Claude가 받을 수 있음 (`handoff.status=ready`, `stage=5`, 담당 `claude`) |
| `on_hold` | 대표가 보류 |
| `done` | 공개·회고까지 끝남 |

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
