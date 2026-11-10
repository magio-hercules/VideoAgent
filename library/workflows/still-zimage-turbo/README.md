# still-zimage-turbo — Z-Image Turbo 텍스트→이미지

레퍼런스 이미지(스타일 앵커, 관통 오브젝트, 장소, 인물 카드)와 정지 컷을 만드는 워크플로.
프롬프트 문법은 `craft/playbooks/z-image-turbo.md`.

## 파일

| 파일 | 역할 |
|---|---|
| `original/image_z_image_turbo.json` | ComfyUI 공식 템플릿 `image_z_image_turbo` (2026-10-08에 가져옴, 로컬 실행 가능 확인) |

원본은 수정하지 않는다. 작업마다 `_infra/shorts-tools/jobgen.py still`로 사본을 만든다.

## 구성

서브그래프 1개("Text to Image (Z-Image-Turbo)"):
`UNETLoader z_image_turbo_bf16` + `CLIPLoader qwen_3_4b (lumina2)` + `VAELoader ae`
→ `ModelSamplingAuraFlow shift 3` → `KSampler 8스텝 cfg 1 res_multistep simple` (네거티브 = ConditioningZeroOut)
→ `EmptySD3LatentImage` → `VAEDecode` → `SaveImage`

## jobgen이 바꾸는 값

| 서브그래프 내부 노드 | 값 |
|---|---|
| #27 CLIPTextEncode text | `--prompt-file` |
| #13 width/height | `--w` / `--h` (기본 768×1344) |
| #3 seed / control / steps | `--seed`, fixed, `--steps` (기본 8) |
| #9 SaveImage prefix | `--prefix` |

## 라이선스

Z-Image-Turbo: Apache-2.0 (Hugging Face 모델 카드, 2026-10-08 확인).
