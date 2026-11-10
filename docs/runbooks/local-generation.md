# 로컬 생성 런북 (ComfyUI)

이 문서는 운영자 PC에서 ComfyUI로 클립·정지 컷·배경음악을 만드는 **점검·실행·전송·복구 절차**를 소유한다.
워크플로 설정은 `library/workflows/`, 모델별 문법과 실패 대응은 `craft/playbooks/`.

**상태: 운영 중** (H3 R2V SpeedX6·I2V 터보, Z-Image Turbo, ACE-Step 1.5). 기준일: 2026-11-10

---

## 1. 점검 루틴 (작업 시작마다, 또는 "에이전트 점검" 요청 시)

| 점검 | 방법 | 실패하면 |
|---|---|---|
| PC 연결 | `device_bash`에서 `ls $HOME/mnt` | 데스크톱 앱에서 열고 PC 연결 요청. 기획 단계만 진행 |
| 서버·GPU | comfy-mcp `server_info` → `server.running` | 운영자 확인 후 기동 |
| 입력·출력 폴더 | `system_stats`의 `argv`에서 `--input-directory` / `--output-directory` | — |
| ComfyUI 루트 | `server_info`의 `workspace.path` | — |
| 이 작업 폴더의 Windows 경로 | `get_device_info`의 `connectedFolders` | 폴더 연결 요청 |
| 디스크 (클립 생성 전) | 여유 30GB 이상 | 정리 요청(삭제는 운영자가) |
| 에피소드 저장소 | Drive 커넥터로 채널 루트 검색(이름은 `private/channel.md`) | 커넥터 켜기 요청 |
| 유료 생성 | 힉스필드 잔여 크레딧 조회 | 커넥터 켜기 요청 |

개인 절대경로는 문서에 적지 않고 매번 위 방법으로 확인한다.
ComfyUI·노드 업데이트 알림이 떠도 제작 중에는 업데이트하지 않는다. H3 워크플로가 깨질 수 있어 운영자 승인과 시험 후에만 한다.

## 2. 모델·워크플로

| 용도 | 모델·워크플로 | 메모 |
|---|---|---|
| 클립 (기본) | MiniMax H3 R2V SpeedX6 (`library/workflows/h3-r2v-speedx6/`) | 0.25MP → 768×1344, 7~8초(175~192프레임), 클립당 약 5~7분 |
| 클립 (구도 유지) | MiniMax H3 I2V + 터보 8스텝 LoRA | 첫 프레임만 입력, 124프레임 이하 |
| 정지 컷·보조 그림 | Z-Image Turbo (`library/workflows/still-zimage-turbo/`) | 768×1344, 8스텝, 장당 약 20초 |
| 배경음악 | ACE-Step 1.5 | MIT 라이선스. seed별로 만들어 고른다 |

하드웨어 기준: Windows 11, RTX 5070 12GB. 다른 GPU에서는 길이·해상도 상한을 다시 잰다.

## 3. 폴더

| 위치 | 내용 |
|---|---|
| 이 폴더 `productions/<종류>/<작품>/` | 작품 문서(BRIEF·생성상태·renders)와 작품별 스크립트 — **Git 제외** |
| ComfyUI 입력 폴더 | R2V·I2V 입력 그림 (`<EP>_bNN.png`, 768×1344) |
| ComfyUI 출력 폴더 `<EP>/` | 생성 중간물: `clips/ jobs/ bgm/ qc/ work/ final/` |
| 에피소드 저장소(Drive) `01_에피소드/EP###_<소재>/` | 채택본·최종본·썸네일·메타 정본. 하위 폴더 `01_기획/ 03_대본/ 04_화면설계/ 05_제작/ 06_편집/ 07_게시준비/ 08_성과/` |

- 편 코드는 `EP###`. 번호는 회차 목록(`private/episode-index.md`)의 다음 번호를 쓴다. 기존 폴더는 덮어쓰지 않는다.
- 없는 단계 폴더는 만들지 않는다. 파일명은 `EP###_<소재>_<유형>_vNN`, 승인본은 `FINAL`, 승인 후 정정은 `FINAL_r1`.

## 4. 실행 절차

1. **작업 JSON 생성** — `device_bash`에서 작업 폴더 루트 기준으로 실행한다. 원본 워크플로는 고치지 않고, 사본에 값만 넣는다.
   - 정지 컷: `python3 _infra/shorts-tools/jobgen.py still --prompt-file … --seed … --prefix VideoAgent/<EP>/refs/<이름> --out productions/…/jobs/<이름>.json`
   - 클립: `python3 _infra/shorts-tools/jobgen.py r2v --prompt-file … --refs <순서대로> --win-root <Windows 경로> --sec 7.5 --seed … --mp 0.25 --prefix VideoAgent/<EP>/b01 --out productions/…/jobs/b01.json`
   - r2v 결과의 `upload_first` 목록을 comfy-mcp `upload_file(overwrite=True)`로 입력 폴더에 먼저 올린다.
2. **검증** — 작품에서 처음 쓰는 워크플로는 `validate_workflow`로 오류 0건을 먼저 확인한다.
3. **제출** — `run_workflow(<작업 JSON Windows 경로>, wait=false)`로 제출하고 `prompt_id`를 `생성상태.md`에 적는다.
4. **대기** — `job(action="status")`만 짧게 부른다. `job wait`·`watch`나 `run_workflow(wait=true)`로 60초 넘게 기다리지 않는다. PC 연결이 끊긴다.
5. **회수** — `fetch_outputs`로 받은 파일(`<id8>_000.mp4`)을 편 규칙 이름(`<EP>_bNN_s<seed>.mp4`)으로 바꾼다. seed는 편 번호 기반으로 겹치지 않게(예: EP027 → 27xx).
6. **검사** — `python3 _infra/shorts-tools/clip_qc.py <clip.mp4>`로 수치 검사와 6프레임 시트를 만든다.
7. **기록** — `renders.md`에 ID·블록·워크플로·seed·결과 파일·판정을 적는다.

## 5. GPU 운용

- H3는 한 번에 하나만 돌린다. 여러 클립은 큐에 순서대로 넣는다.
- 정지 컷(Z-Image)을 모두 끝낸 뒤 클립(H3)을 돌린다. 모델을 번갈아 올리면 느려진다.
- 10초(243프레임) 이상은 생성하지 않는다. PC가 멈춘 기록이 있다.
- 생성 전에 예상 시간(클립 수 × 5~7분)을 운영자에게 알린다.
- `job cancel`은 interrupt도 함께 보낸다. 이미 끝난 작업을 취소하면 지금 돌던 작업이 끊길 수 있다.

## 6. 클라우드 ↔ PC 파일 전송

- **PC → 클라우드:** `device_stage_files`. 연결 폴더 아래 7단계 깊이까지만 된다. 더 깊으면 PC 셸로 얕은 경로에 복사한 뒤 보낸다.
- **클라우드 → PC:** `device_commit_files`. 이미지·mp3·mp4·jpg를 그대로 보내면 내용이 바뀌어 md5가 틀어진다. gzip으로 보내고 PC에서 풀어 md5를 확인한다. 큰 파일은 9MB로 나눠 보내고 합친 뒤 확인한다.
- **다시 보낼 때:** 같은 이름이면 예전 내용이 갈 수 있다. 매번 새 이름이나 v2·v3 하위 폴더를 쓴다.
- **PC 셸 제약:** 한 번에 최대 3분. 백그라운드 프로세스는 호출이 끝나면 죽는다. 큰 영상을 메모리에 통째로 올리면 강제 종료된다. 긴 렌더는 클라우드에서 한다.
- **폴더 이름:** 운영자가 폴더 이름을 바꾸는 경우가 있다. 보내기 전에 폴더 목록을 확인한다.
- **삭제:** 권한이 없다. 지울 파일은 남겨 두고 `생성상태.md`의 '대표 확인 대기'에 적는다.
- **클라우드 pip 설치:** 멈추면 `--timeout 30`으로 다시 시도한다. LaMa 설치는 10분 넘게 걸릴 수 있다.

## 7. 복구

- 서버가 꺼지면 `get_logs`로 마지막 줄을 확인해 원인을 알리고, 운영자 확인 후 1회만 다시 띄운다.
- OOM(메모리 부족)이면 `--mp`를 한 단계 낮추거나 클립을 짧게 나눈다.
- 디스크 부족은 엉뚱한 오류로 나타난다(→ `craft/playbooks/minimax-h3-r2v.md` §7).
- 같은 입력을 다시 제출하면 캐시된 결과가 나온다. 새 결과가 필요하면 seed를 바꾼다.

## 8. 승인이 필요한 일 (AGENTS.md 승인 경계)

ComfyUI 기동·재시작·업데이트, 모델·커스텀 노드·Python 패키지 설치, 큐잉, 대용량 다운로드.
