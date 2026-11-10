# 워크플로 라이브러리

워크플로(예: ComfyUI JSON) 하나당 폴더 하나를 둔다.

## 규칙

- 위치: `library/workflows/{워크플로}/`
- 각 폴더의 `README.md`가 그 워크플로의 정확한 설정(필요 모델, 노드, 입력·출력)을 소유한다.
- 받은 원본은 `original/`에 그대로 두고 수정하지 않는다. 용도별 사본은 폴더 바로 아래에 두고 README에 변경점을 적는다.
- 작업용 JSON은 `_infra/shorts-tools/jobgen.py`로 사본에서 만들어 작품 폴더 `jobs/`에 둔다.
- 필요한 모델·노드 설치는 사용자의 명시적 요청이 있을 때만 한다.
- **공개 저장소에는 README만 올린다.** 워크플로 JSON과 동봉 코드는 배포 권리를 확인하기 전까지 Git에서 제외한다(`.gitignore`). 받는 곳은 각 README에 적는다.

## 색인

| 워크플로 | 폴더 | 용도 | 상태 |
|---|---|---|---|
| MiniMax H3 R2V SpeedX6 | `h3-r2v-speedx6/` | 쇼츠 클립 (대표 그림 → 영상) | 운영 중 |
| Z-Image Turbo T2I | `still-zimage-turbo/` | 정지 컷·보조 그림 | 운영 중 |
