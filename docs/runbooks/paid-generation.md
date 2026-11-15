# 유료 생성 런북

이 문서는 Claude 쪽에서 크레딧이 드는 생성(나레이션, 대표가 지시한 경우의 썸네일 바탕)의 **승인·실행·기록 절차**를 소유한다.
모델별 요령은 `craft/playbooks/gpt-image.md`, `craft/playbooks/post-production.md`.

**상태: 연결됨** — 힉스필드 MCP 커넥터(로그인 방식, 저장소에 키 없음). 기준일: 2026-11-11

## 1. 쓰는 서비스

| 용도 | 모델 | 단계 | 실측 비용 |
|---|---|---|---|
| 나레이션 | 힉스필드 MCP `generate_audio` · 모델 `elevenlabs_v4` + 운영자 보이스(element) | 6 | 편당 약 2~10크레딧 (EP030 실측 견적 3.22) |
| 썸네일 바탕 그림 (대표 지시 때만) | `gpt_image_2_6` | 9 | 2K·high 장당 약 2.75크레딧 |

- **그림(스타일 시안·대표 그림·썸네일 바탕)은 기본적으로 여기서 만들지 않는다.** Codex CLI 이미지 생성(ChatGPT 계정)으로 만든다(→ `craft/playbooks/gpt-image.md`, 도구 `_infra/codex-imagegen/`). 대표가 따로 지시할 때만 힉스필드로 만들고, 그때도 아래 절차를 따른다.

- **나레이션은 힉스필드 MCP로만 만든다.** ElevenLabs를 직접 부르는 커넥터·API나 로컬 TTS(Chatterbox)는 쓰지 않는다(이유 → `craft/playbooks/post-production.md` §1).

보이스 이름·ID는 `.env`의 `NARRATION_VOICE_NAME`·`NARRATION_VOICE_ELEMENT_ID`를 쓴다. 값을 문서·로그에 쓰지 않는다.
가격·크레딧 잔액은 금방 낡으므로 위 실측은 참고로만 쓰고, 매번 견적을 다시 낸다.

## 2. 항상 지킬 규칙

- 비용이 드는 생성(유료·무료 크레딧 포함)은 매번 운영자의 명시적 승인 후에만 한다.
- 승인 전에 예상 비용·생성 개수·모델을 먼저 보여준다.
- 실패했다고 자동으로 재시도하지 않는다(재시도도 비용이다).
- 계정 연결, 로그인, 토큰 입력은 운영자가 직접 요청할 때만 한다.
- **편당 크레딧 상한:** 운영자가 "EP### 크레딧 상한 N"을 주면 그 범위 안에서는 다시 묻지 않는다. 넘을 것 같으면 멈추고 묻는다.

## 3. 절차

1. 견적: 생성 도구에 `get_cost: true`를 넣어 제출 없이 비용만 받는다(나레이션은 아래 §4와 같은 파라미터 그대로). 개수 × 단가를 운영자에게 보인다.
2. 승인을 받는다(또는 편당 상한 안인지 확인).
3. 생성: 이미지는 `generate_image_batch`(최대 12개씩), 나레이션은 §4.
4. 대기: `jobs_wait`(짧은 timeout)로 확인한다.
5. 회수·저장: 결과를 에피소드 폴더의 해당 단계 하위 폴더에 저장한다.
6. 기록: `renders.md`에 모델·개수·실제 크레딧·결과 파일·채택 여부를 적는다.

## 4. 나레이션 (힉스필드 MCP) — 2026-11-11 EP030 실행 기준

| 순서 | 도구·값 | 메모 |
|---|---|---|
| 1. 보이스 확인 | `list_voices` → `voice_type: element`인 운영자 보이스의 `voice_id` | `.env`의 `NARRATION_VOICE_ELEMENT_ID`와 같은 값이다. 에이전트가 `.env`를 읽을 수 없는 환경(권한 정책)에서는 이 목록에서 운영자 계정 전용 element를 고른다. 후보가 여럿이거나 확실하지 않으면 운영자에게 묻는다 |
| 2. 저장 위치 설정 | `get_preferences` | `auto_create_project: false`면 `folder_id` 없이 생성한다 |
| 3. 견적 | `generate_audio` · `model: elevenlabs_v4` · `dialogue` · `get_cost: true` | 아래 형식 그대로. 결과 `credits`를 운영자에게 보인다 |
| 4. 승인 | 운영자 명시 승인 또는 편당 상한 | §2 |
| 5. 생성 | 같은 호출에서 `get_cost`만 뺀다 | 한 번만 제출. 응답의 job `id`를 적어 둔다. 전송 시간 초과면 결과를 확인하기 전에 다시 제출하지 않는다 |
| 6. 대기 | `jobs_wait`(timeout ≤15초, `poll_after_seconds`만큼 쉬고 반복) | `completed`면 `result_url`(mp3)이 온다 |
| 7. 회수 | `result_url`을 작품 폴더 `05_제작/나레이션/<EP>_narration_<대본버전>_take<n>.mp3`로 내려받는다 | 덮어쓰지 않는다. 길이·md5를 `renders.md`에 적는다 |

`dialogue` 형식 — **블록 하나 = 턴 하나**, 발화용(TTS) 원고 그대로, 모든 턴에 같은 보이스:

```json
[
  {"text": "<B01 발화용 원고>", "voice_type": "element", "voice_id": "<운영자 보이스 element ID>"},
  {"text": "<B02 발화용 원고>", "voice_type": "element", "voice_id": "<같은 ID>"}
]
```

- 분할 블록(B05a·B05b)은 턴을 나눈다. 블록 사이 쉼은 모델이 0.1~0.35초로 둔다.
- 총 10,000자 이하. 한 테이크면 편당 수 크레딧이라 블록별 개별 생성보다 싸고 자연스럽다.
- 받은 뒤 할 일(실측 타임라인·판정 기준 확정)은 `craft/doctrine/planning.md` §6, 받아쓰기·분할 요령은 `craft/playbooks/post-production.md` §2.
