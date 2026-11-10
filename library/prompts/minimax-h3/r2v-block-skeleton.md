# R2V 클립 프롬프트 골격 (장면 1개, 7~8초)

- 대상 모델: MiniMax H3 R2V (워크플로 `h3-r2v-speedx6`)
- 용도: 얼굴 없는 내레이션 쇼츠의 장면 하나(블록 하나에 장면 1~2개)
- 검증: 형식 검증됨(실제 제작에 사용). 문장 예시는 편마다 바꾼다
- 문법 규칙과 내용 점검 6항목: `craft/playbooks/minimax-h3-r2v.md`

`{…}`를 채워 블록별 `prompts/bNN.txt`로 저장한다. `{공통 스타일 문장}`은 그 편 `BRIEF.md` §5의 문장을 바이트 그대로 붙인다.
고정 문장에는 `<Picture 1>`에 **실제로 그려진 것만** 쓴다.

```
subject_definitions:
<Subject 1> is the art style of <Picture 1>: {공통 스타일 문장}.
<Subject 2> is the {그 그림에 그려진 핵심 인물·사물 고정 묘사} seen in <Picture 1>.

summary:
[reference generation] A short vertical explainer shot in which {이 장면이 보여 줄 한 가지}. <Subject 1> and <Subject 2> come from <Picture 1>.

retention_analysis:
<Subject 1>: fully_preserved - the look, palette, line and texture of <Picture 1> stay the same for the whole video.
<Subject 2>: fully_preserved - remains the exact same {인물·사물} from <Picture 1>, preserving its shape, proportions, colors and markings. The preserved identity covers its form and surface, while the shot freely directs only a small movement.

detailed_description:
{공통 스타일 문장}. A locked-off static camera faces the scene straight-on for the whole video. The lighting and colors stay exactly as in <Picture 1>. Figures stay silent with closed mouths and communicate only through gestures. All labels and signs stay blank with no markings. Key subjects stay in the upper part of the frame.
{화면 속 위치}의 <Subject 2> {작은 동작 하나}, {눈에 보이는 결과}. Everything else stays still and fully drawn; nothing new appears and nothing disappears.

overall_soundscape:
{화면 사건의 효과음만: soft paper rustle, a light tap …}

non_diegetic_music:
N/A
```
