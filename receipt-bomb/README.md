# 영수증 폭탄 (Receipt Bomb)

밥값 내기 복불복 미니게임. 한 명씩 돌아가며 "카드 긁기"를 누르다가 결제가 **승인**되는 사람이 오늘 밥값 담당.

- 게임 코드 전체: `src/App.jsx` (파일 하나)
- React 18 + Tailwind CSS v4 + Vite

## 로컬 실행

```bash
npm install
npm run dev      # 같은 와이파이의 폰에서 표시되는 Network 주소로 접속
```

## Vercel 배포

1. Vercel에서 이 저장소를 Import
2. **Root Directory**를 `receipt-bomb`로 지정 (Framework: Vite 자동 인식)
3. Deploy → 나오는 주소를 폰에서 열면 끝

## 폰에서 바로 여는 단일 파일 버전

`npm run build:single` → `play/index.html` 하나에 모든 코드가 들어갑니다.
이 파일은 저장소에 커밋되어 있어서 GitHub Pages가 켜져 있으면
`https://hyun07cho.github.io/hyun07cho/receipt-bomb/play/` 로 열 수 있습니다.

## 참고

- 진동(`navigator.vibrate`)은 안드로이드 크롬에서 동작합니다. iOS Safari는 진동 API를 지원하지 않아 조용히 건너뜁니다.
- 소리는 첫 터치("게임 시작") 이후에 재생됩니다 (모바일 브라우저 정책). 오른쪽 위 🔊 버튼으로 끌 수 있습니다.
