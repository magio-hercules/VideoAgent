# h3-r2v-speedx6 — MiniMax H3 Reference-to-Video (SpeedX6)

쇼츠 클립 생성의 **주 워크플로** (운영 중). 이 문서가 이 워크플로의 정확한 설정을 소유한다.
프롬프트 문법은 `craft/playbooks/minimax-h3-r2v.md`, 실행 절차는 `docs/runbooks/local-generation.md`.

## 파일

| 파일 | 역할 | 수정 |
|---|---|---|
| `original/minimaxSpeedX6Workflow_v10.json` | 대표가 제공한 원본 (SHA-256 `ca7d4c61…406e`) | 금지 |
| `original/sol_attn_minimax_pr117/__init__.py` | `SolAttnMiniMax` 어댑터 노드 원본 (SHA-256 `2A2D2C99…861B`, 워크플로 노트의 검증 해시와 일치) | 금지 |
| `shorts_r2v_9x16.json` | 쇼츠용 사본 — 아래 "원본 대비 변경" 적용 | 변경 시 이 문서 갱신 |

작업마다 `_infra/shorts-tools/jobgen.py r2v`로 `shorts_r2v_9x16.json`의 사본을 만들어 쓴다. 사본 자체를 직접 고치지 않는다.

## 생성 경로 (원본 계약)

`UNETLoader(ref2va) → PathchSageAttentionKJ → SolAttnMiniMax`
→ `BasicScheduler simple 20스텝 → SplitSigmas 15+5`
→ 1단계 15스텝(시작 해상도) → `LTXVSeparateAVLatent` → 영상 잠재만 `MinimaxH3LatentUpscaler3D` ×2 (오디오는 우회) → `LTXVConcatAVLatent`
→ 2단계 5스텝(최종 해상도) → `VAEDecode` + `VAEDecodeAudio` → `VHS_VideoCombine` (24fps, h264 mp4, 소리 포함)

- 샘플러 `res_multistep`, 스케줄러 `simple`, 20스텝 15+5 분할은 A/B 실험이 아니면 바꾸지 않는다.
- 원본 노트 지시: Turbo LoRA·Fused Modulation·Spectrum·Sigma Shift·Ultimate SD Upscale을 생성 경로에 넣지 않는다.
- 오른쪽 후처리 섬(RTX 디블러+업스케일, RIFE 60fps)은 우회 상태로 둔다. 쇼츠는 24fps로 납품한다.

## 원본 대비 변경 (`shorts_r2v_9x16.json`)

| 노드 | 원본 | 쇼츠 사본 | 이유 |
|---|---|---|---|
| #128 CLIPLoader | `qwen3vl_32b_minimax_h3_int8_convrot` | `qwen3vl_32b_minimax_h3_nvfp4_awq` | 설치된 파일. 원본 노트가 허용한 대안이고 RTX 5070(Blackwell)이 NVFP4를 지원 |
| #119 VAELoader | `minimax_h3_video_vae_fp16` | `minimax_h3_video_vae_int8_convrot` | 설치된 파일 (스모크 테스트로 화질 확인) |
| #186 업스케일러 모델 | `minimax_h3_latent_upscaler_3d_bf16` | `minimax_h3_latent_upscaler_3d_conv_v1_bf16` | 배포처(HF) 실제 파일명이 다름 |
| #145 시작 해상도 | 16:9 / 0.15MP | 9:16 / 0.25MP | 쇼츠 세로. 최종 = 가로세로 2배 |
| #132 Duration | 5초 | 10초 | 사본의 기본값. 실제 길이는 jobgen `--sec`로 넣는다: 표준 7~8초(175~192프레임). 10초 이상은 PC가 멈춘 기록이 있어 쓰지 않는다 |
| #129 RandomNoise | randomize | fixed (seed 101) | 재현성 |
| #144 저장 접두어 | AnimateDiff | `VideoAgent/clip` | 출력 폴더 정리 |
| #181 Sage | auto | **disabled** | SageAttention·Triton이 설치돼 있지 않음 (2026-10-08 확인) |
| #192 Sol | `SolAttnMiniMax` (동봉 어댑터) | **`BlockSparseAttention`** (ComfyUI 내장) `["sol-attn", tau 1.3, start 0.2, end 0.9, dense "", min_tokens 12288, extra_tokens 256, exact_kv_and_rows, verbose false]` | 아래 설명 |

#127 UNET(`minimax_h3_ref2va_pruned_int8_convrot`)은 원본 그대로다.

**Sol 노드를 바꾼 이유**
- 동봉 어댑터는 comfy-kitchen PR #117(초안)의 함수 형태를 쓴다(`sol_attn_workspace_bytes`, `max_blocks`, `centroid_tail`, `workspace`).
- 설치된 comfy-kitchen 0.2.36에는 Sol-Attn이 정식으로 들어와 있지만 함수 형태가 다르다(`tail`, `topk_ratio`, `token_aug`). 그래서 어댑터를 넣으면 실행 중 오류가 난다.
- ComfyUI 0.38.2에는 같은 커널을 쓰는 내장 노드 `BlockSparseAttention`이 있다. MiniMax H3 전용 경로(QKV를 4K 토큰씩 나눠 바로 커널로 보내는 방식)와 조건부 sink(`exact_kv_and_rows`)를 지원한다. 그래서 어댑터 대신 이 노드를 쓴다.
- 원본의 `routed_cap_percent 30`에 해당하는 설정은 내장 노드에 없다. 대신 `extra_tokens 256`(권장값)을 쓴다. 화질과 속도는 스모크 테스트로 확인한다.
- 동봉 어댑터(`original/sol_attn_minimax_pr117/`)는 설치하지 않고 참고용으로만 보관한다.

## jobgen이 바꾸는 값

| 노드·위젯 | 값 |
|---|---|
| #141 prompt | 6섹션 R2V 프롬프트 (`--prompt-file`) |
| #142 image_paths | 레퍼런스 Windows 절대경로, 줄바꿈 구분, 순서 = `<Picture n>` (형식은 스모크 테스트로 확인 필요) |
| #132 Duration | `--sec` (프레임 = 17k+5 격자, 최대 243 = 10.125초) |
| #129 seed | `--seed`, fixed |
| #145 ratio / megapixels | `--ratio` / `--mp` |
| #144 filename_prefix | `--prefix` |
| #181 sage | `--sage` |
| #192 verbose (위젯 8번) | `--verbose-sol` (첫 검증 실행만 켬) |

## 해상도 프로필 (시작 → 최종, 9:16, 배수 32)

| 프로필 | `--mp` | 시작 | 최종 | 용도 |
|---|---|---|---|---|
| smoke | 0.15 | 약 288×512 | 약 576×1024 | 설치 검증 |
| std | 0.25 | 384×672 | 768×1344 | 기본 제작 → 조립에서 1080×1920 확대. **실측(2026-10-08): 3초(73프레임) 클립 298초** — 1단계 15스텝 82초(5.5초/스텝, 6,711토큰이라 dense), 2단계 5스텝 49초(23,343토큰, sparse 작동), 나머지는 모델 로드·디코드 |
| hq | 0.5 | 약 544×960 | 약 1088×1920 | 12GB에서 가능 여부 미확인 |

정확한 크기는 `DenoResolutionSetup`이 정한다. 짧은 클립은 1단계 토큰이 `min_tokens`(12,288)보다 적어 dense로 돌고, 2단계에서만 sparse가 작동한다.

## 의존성 상태 (2026-10-08 점검)

| 항목 | 상태 |
|---|---|
| deno-custom-nodes (`DenoMiniMaxH3ReferenceToVideo`, `…ReferenceImageLoader`, `DenoResolutionSetup`, `DenoTextEncoderUnload`) | 설치됨 (0.7.109) |
| KJNodes (`PathchSageAttentionKJ`) | 설치됨 (1.5.0) |
| VideoHelperSuite (`VHS_VideoCombine`) | 설치됨 |
| core `LTXVSeparateAVLatent` / `LTXVConcatAVLatent` / `ComfyMathExpression` | 있음 (ComfyUI 0.38.2) |
| comfy-kitchen CUDA `sol_attn` + 내장 `BlockSparseAttention` | 있음 (0.2.36 / ComfyUI 0.38.2). 실제 sparse 동작은 스모크 테스트 로그로 확인 |
| UNET `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 설치됨 (19.5GB, `models/diffusion_models/`). 2026-10 이후 제작에 사용 중 |
| 노드 `MinimaxH3LatentUpscaler3D` | **설치됨** — `custom_nodes/Comfyui_Minimax_h3_latent_Upscaler/`, 커밋 `40316cf`, 코드 검토 완료(네트워크·외부 명령 없음). ComfyUI 재시작 후 인식 |
| 모델 `minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors` | **설치됨** (0.66GB, `models/latent_upscale_models/`) |
| SageAttention / Triton | 없음 → #181 disabled |
| 선택: ComfyUI-VFI(RIFE), realesr 업스케일 모델 | 쓰지 않음 |

ComfyUI 워크플로 목록(`user/default/workflows/VideoAgent/`)에 세 파일을 넣었다.
- `쇼츠_H3_R2V_SpeedX6_9x16.json` — 이 폴더의 쇼츠 사본과 같은 파일
- `쇼츠_ZImage_레퍼런스_정지컷.json`
- `참고_SpeedX6_원본_v10.json` — 어댑터가 없어서 Sol 노드가 빨갛게 표시된다. 참고용

## 라이선스

MiniMax H3 Community License(2026-08-02). 라이선스에 제외 지역이 있으므로 사용 전에 본인 지역을 확인한다. 사용 여부는 운영자가 결정해 `private/decisions.md`에 남기고, 게시 전 라이선스가 바뀌었는지 다시 확인한다.

## 받는 곳 (저장소에 포함하지 않음)

- 원본 워크플로 `minimaxSpeedX6Workflow_v10.json`과 동봉 어댑터는 배포 권리를 확인하지 못해 공개 저장소에서 제외한다. 배포처에서 직접 받아 `original/`에 둔다.
- 모델 파일은 Hugging Face `Comfy-Org/MiniMax-H3` 저장소에서 받는다.

## 스모크 테스트 통과 기준

1. 검증(`validate_workflow`)에 오류 0건.
2. `smoke` 프로필, 5초, 레퍼런스 1장, Sol `verbose`를 켜고 1회 실행.
3. 로그에 `BlockSparseAttention: sparse producer path`가 1줄 이상 있고, CUDA 오류가 없음.
4. 재생 가능한 MP4(영상+소리)가 생성됨. 소요 시간과 VRAM 최대치를 위 프로필 표에 기록.
