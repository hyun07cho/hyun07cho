import { useCallback, useEffect, useRef, useState } from 'react'

/* =========================================================================
 * 영수증 폭탄 (Receipt Bomb)
 * 한 명씩 돌아가며 카드를 긁다가 "결제 승인"이 뜨는 사람이 오늘 밥값 담당.
 * 파일 하나로 끝나는 게임: 커스텀 keyframes·폰트 클래스는 아래 <style>에 있음.
 * ========================================================================= */

const MIN_PLAYERS = 2
const MAX_PLAYERS = 10
const PROCESSING_MS = 650 // "승인 중..." 뜸 들이는 시간 (긴장감)
const PASS_POPUP_MS = 500 // "통과!" 팝업 시간
const BOOM_MS = 1600 // 폭발 연출 후 결과 화면으로

const GAME_CSS = `
.font-display { font-family: 'Black Han Sans', 'Gothic A1', system-ui, sans-serif; letter-spacing: -0.01em; }
.font-body { font-family: 'Gothic A1', system-ui, -apple-system, 'Apple SD Gothic Neo', sans-serif; }
.font-receipt { font-family: 'Nanum Gothic Coding', ui-monospace, 'SFMono-Regular', Menlo, monospace; }
.neon-pink { color: #ff3d9a; text-shadow: 0 0 6px rgba(255,61,154,.8), 0 0 22px rgba(255,61,154,.55); }
.neon-cyan { color: #3ff3ff; text-shadow: 0 0 6px rgba(63,243,255,.8), 0 0 22px rgba(63,243,255,.5); }
.neon-green { color: #4dff9b; text-shadow: 0 0 8px rgba(77,255,155,.9), 0 0 30px rgba(77,255,155,.6); }
.lcd { color: #b6ffcf; text-shadow: 0 0 6px rgba(120,255,170,.7); }
.no-tap { -webkit-tap-highlight-color: transparent; touch-action: manipulation; user-select: none; -webkit-user-select: none; }
.bg-grid {
  background-color: #0b0614;
  background-image:
    radial-gradient(ellipse at 50% -10%, rgba(255,61,154,.22), transparent 55%),
    radial-gradient(ellipse at 50% 120%, rgba(63,243,255,.16), transparent 55%),
    linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px);
  background-size: auto, auto, 28px 28px, 28px 28px;
}
.barcode { background: repeating-linear-gradient(90deg, #1b1b1b 0 2px, transparent 2px 4px, #1b1b1b 4px 5px, transparent 5px 8px, #1b1b1b 8px 11px, transparent 11px 12px); }
.zigzag-bottom { --z: 8px; -webkit-mask: conic-gradient(from -45deg at bottom, #0000, #000 1deg 89deg, #0000 90deg) 50% / calc(var(--z) * 2) 100%; mask: conic-gradient(from -45deg at bottom, #0000, #000 1deg 89deg, #0000 90deg) 50% / calc(var(--z) * 2) 100%; padding-bottom: var(--z); }

@keyframes rb-shake {
  0%, 100% { transform: translate(0, 0) rotate(0); }
  10% { transform: translate(-14px, 6px) rotate(-2deg); }
  20% { transform: translate(12px, -8px) rotate(2deg); }
  30% { transform: translate(-10px, -4px) rotate(-1.5deg); }
  40% { transform: translate(10px, 8px) rotate(1.5deg); }
  50% { transform: translate(-8px, 4px) rotate(-1deg); }
  60% { transform: translate(8px, -6px) rotate(1deg); }
  70% { transform: translate(-6px, 2px) rotate(-.5deg); }
  80% { transform: translate(4px, -2px) rotate(.5deg); }
  90% { transform: translate(-2px, 1px) rotate(0); }
}
@keyframes rb-flash {
  0%, 20%, 40%, 60% { opacity: .95; }
  10%, 30%, 50% { opacity: .15; }
  100% { opacity: .55; }
}
@keyframes rb-pop {
  0% { transform: translate(-50%, -50%) scale(.3); opacity: 0; }
  35% { transform: translate(-50%, -50%) scale(1.15); opacity: 1; }
  70% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
  100% { transform: translate(-50%, -60%) scale(.95); opacity: 0; }
}
@keyframes rb-beat {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255,61,154,.0), 0 0 40px rgba(255,61,154,.25); }
  12% { transform: scale(1.025); box-shadow: 0 0 0 8px rgba(255,61,154,.25), 0 0 60px rgba(255,61,154,.45); }
  24% { transform: scale(1); }
  36% { transform: scale(1.015); box-shadow: 0 0 0 4px rgba(255,61,154,.15), 0 0 50px rgba(255,61,154,.35); }
}
@keyframes rb-print {
  0% { transform: translateY(-100%); }
  100% { transform: translateY(0); }
}
@keyframes rb-blink { 0%, 100% { opacity: 1; } 50% { opacity: .2; } }
@keyframes rb-rise { 0% { transform: translateY(18px); opacity: 0; } 100% { transform: translateY(0); opacity: 1; } }
@keyframes rb-swipe {
  0% { transform: translateX(-60%) rotate(-8deg); opacity: 0; }
  30% { opacity: 1; }
  100% { transform: translateX(60%) rotate(-8deg); opacity: 0; }
}
@keyframes rb-glow { 0%, 100% { filter: brightness(1); } 50% { filter: brightness(1.25); } }

@media (prefers-reduced-motion: reduce) {
  .motion-safe-only { animation: none !important; }
}
`

/* ---------- 진동 (지원하는 기기만) ---------- */
function vibrate(pattern) {
  try {
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
      navigator.vibrate(pattern)
    }
  } catch {
    /* iOS Safari 등 미지원 기기는 조용히 무시 */
  }
}

/* ---------- 효과음 (Web Audio로 직접 합성, 파일 없음) ---------- */
function useSound(muted) {
  const ctxRef = useRef(null)

  const ensure = useCallback(() => {
    try {
      if (!ctxRef.current) {
        const AC = window.AudioContext || window.webkitAudioContext
        if (!AC) return null
        ctxRef.current = new AC()
      }
      if (ctxRef.current.state === 'suspended') ctxRef.current.resume()
      return ctxRef.current
    } catch {
      return null
    }
  }, [])

  const tone = useCallback(
    (freq, dur, { type = 'sine', gain = 0.3, delay = 0, endFreq } = {}) => {
      if (muted) return
      const ctx = ensure()
      if (!ctx) return
      const t = ctx.currentTime + delay
      const osc = ctx.createOscillator()
      const g = ctx.createGain()
      osc.type = type
      osc.frequency.setValueAtTime(freq, t)
      if (endFreq) osc.frequency.exponentialRampToValueAtTime(endFreq, t + dur)
      g.gain.setValueAtTime(0.0001, t)
      g.gain.exponentialRampToValueAtTime(gain, t + 0.01)
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur)
      osc.connect(g).connect(ctx.destination)
      osc.start(t)
      osc.stop(t + dur + 0.05)
    },
    [muted, ensure],
  )

  const noise = useCallback(
    (dur, gain = 0.4) => {
      if (muted) return
      const ctx = ensure()
      if (!ctx) return
      const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * dur), ctx.sampleRate)
      const data = buf.getChannelData(0)
      for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length)
      const src = ctx.createBufferSource()
      const g = ctx.createGain()
      g.gain.value = gain
      src.buffer = buf
      src.connect(g).connect(ctx.destination)
      src.start()
    },
    [muted, ensure],
  )

  return {
    unlock: ensure,
    heartbeat: () => {
      tone(70, 0.14, { gain: 0.55, endFreq: 40 })
      tone(62, 0.16, { gain: 0.4, endFreq: 36, delay: 0.2 })
    },
    swipe: () => {
      tone(900, 0.06, { type: 'square', gain: 0.06 })
      tone(900, 0.06, { type: 'square', gain: 0.06, delay: 0.18 })
      tone(900, 0.06, { type: 'square', gain: 0.06, delay: 0.36 })
    },
    pass: () => {
      tone(1320, 0.08, { type: 'triangle', gain: 0.25 })
      tone(1760, 0.14, { type: 'triangle', gain: 0.25, delay: 0.09 })
    },
    boom: () => {
      noise(0.9, 0.5)
      tone(220, 0.9, { type: 'sawtooth', gain: 0.35, endFreq: 40 })
      tone(880, 0.25, { type: 'square', gain: 0.12, delay: 0.05 })
      tone(880, 0.25, { type: 'square', gain: 0.12, delay: 0.4 })
    },
    print: () => {
      for (let i = 0; i < 14; i++) tone(2400 + (i % 2) * 300, 0.02, { type: 'square', gain: 0.03, delay: i * 0.12 })
    },
  }
}

/* ---------- 영수증 문구 ---------- */
const MENU_POOL = [
  ['삼겹살 3인분', 45000],
  ['차돌 된장찌개', 9000],
  ['공기밥 추가', 2000],
  ['치즈 계란말이', 12000],
  ['후라이드 반 양념 반', 21000],
  ['생맥주 500cc', 5000],
  ['음료수', 2500],
  ['디저트 빙수', 13000],
  ['떡볶이 세트', 16000],
  ['마라탕 2단계', 14000],
  ['소고기 추가', 32000],
  ['양념갈비 2인분', 38000],
]

function pickItems(players) {
  const pool = [...MENU_POOL].sort(() => Math.random() - 0.5)
  const count = Math.min(4 + Math.floor(players / 3), 6)
  return pool.slice(0, count).map(([name, price]) => {
    const qty = 1 + Math.floor(Math.random() * Math.max(1, Math.ceil(players / 3)))
    return { name, qty, price: price * qty }
  })
}

const won = (n) => n.toLocaleString('ko-KR')

/* =========================================================================
 * App
 * ========================================================================= */
export default function App() {
  const [gameState, setGameState] = useState('start') // 'start' | 'playing' | 'result'
  const [players, setPlayers] = useState(4)
  const [currentTurn, setCurrentTurn] = useState(1) // 지금 누를 차례 (1부터)
  const [bombTurn, setBombTurn] = useState(1) // 당첨 순서
  const [phase, setPhase] = useState('idle') // 'idle' | 'processing' | 'pass' | 'boom'
  const [muted, setMuted] = useState(false)
  const [receipt, setReceipt] = useState(null)

  const timers = useRef([])
  const sound = useSound(muted)

  const later = (fn, ms) => {
    const id = setTimeout(fn, ms)
    timers.current.push(id)
  }
  const clearTimers = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
  }
  useEffect(() => clearTimers, [])

  /* 심장 박동: 차례가 진행될수록 빨라짐 (당첨 순서와는 무관하게 → 스포일러 없음) */
  const progress = players > 1 ? (currentTurn - 1) / (players - 1) : 0
  const beatMs = phase === 'processing' ? 420 : Math.round(1000 - progress * 480)

  useEffect(() => {
    if (gameState !== 'playing' || phase === 'boom' || phase === 'pass') return
    sound.heartbeat()
    const id = setInterval(sound.heartbeat, beatMs)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameState, phase, beatMs, muted])

  const startGame = () => {
    sound.unlock() // 모바일은 사용자 터치가 있어야 소리가 남
    clearTimers()
    setBombTurn(1 + Math.floor(Math.random() * players))
    setCurrentTurn(1)
    setPhase('idle')
    setReceipt(null)
    setGameState('playing')
    vibrate(30)
  }

  const goHome = () => {
    clearTimers()
    setPhase('idle')
    setGameState('start')
  }

  const pay = () => {
    if (phase !== 'idle') return
    sound.unlock()
    setPhase('processing')
    sound.swipe()
    vibrate(20)

    later(() => {
      if (currentTurn === bombTurn) {
        // 💥 당첨
        setPhase('boom')
        vibrate([500, 100, 500])
        sound.boom()
        const items = pickItems(players)
        setReceipt({
          items,
          total: items.reduce((s, i) => s + i.price, 0),
          at: new Date(),
          no: String(Math.floor(100000 + Math.random() * 900000)),
        })
        later(() => {
          setGameState('result')
          sound.print()
        }, BOOM_MS)
      } else {
        // ✅ 통과
        setPhase('pass')
        vibrate([50])
        sound.pass()
        later(() => {
          setCurrentTurn((t) => t + 1)
          setPhase('idle')
        }, PASS_POPUP_MS)
      }
    }, PROCESSING_MS)
  }

  return (
    <div className="font-body no-tap relative h-[100dvh] break-keep w-full overflow-hidden bg-grid text-white">
      <style>{GAME_CSS}</style>

      {/* 소리 켜기/끄기 */}
      <button
        type="button"
        onClick={() => setMuted((m) => !m)}
        aria-label={muted ? '소리 켜기' : '소리 끄기'}
        className="absolute right-4 top-[max(1rem,env(safe-area-inset-top))] z-40 grid h-12 w-12 place-items-center rounded-full border border-white/15 bg-white/5 text-2xl backdrop-blur transition active:scale-90"
      >
        {muted ? '🔇' : '🔊'}
      </button>

      {gameState === 'start' && <SetupScreen players={players} setPlayers={setPlayers} onStart={startGame} />}

      {gameState === 'playing' && (
        <PlayScreen
          players={players}
          currentTurn={currentTurn}
          phase={phase}
          beatMs={beatMs}
          onPay={pay}
          onQuit={goHome}
        />
      )}

      {gameState === 'result' && (
        <ResultScreen players={players} bombTurn={bombTurn} receipt={receipt} onRetry={startGame} onHome={goHome} />
      )}
    </div>
  )
}

/* =========================================================================
 * 1. 시작 화면
 * ========================================================================= */
function SetupScreen({ players, setPlayers, onStart }) {
  const change = (d) => {
    setPlayers((p) => Math.min(MAX_PLAYERS, Math.max(MIN_PLAYERS, p + d)))
    vibrate(15)
  }

  return (
    <main className="mx-auto flex h-full max-w-md flex-col px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-[max(1.5rem,env(safe-area-inset-top))]">
      <header className="mt-6 text-center">
        <p className="neon-cyan font-receipt text-sm font-bold tracking-[0.3em]">RECEIPT BOMB</p>
        <h1 className="font-display mt-3 text-[2.6rem] leading-[1.1] [text-wrap:balance]">
          오늘의 <span className="neon-pink">결제 요정</span>은
          <br />
          누구? 🧚
        </h1>
        <p className="mt-4 text-[1.05rem] leading-relaxed text-white/70">
          한 명씩 돌아가며 카드를 긁어요.
          <br />
          <b className="text-white">결제가 승인되는 사람</b>이 오늘 밥값 담당!
        </p>
      </header>

      <section className="my-auto flex flex-col items-center gap-5">
        <p className="text-lg font-bold text-white/80">몇 명이서 먹었나요?</p>
        <div className="flex w-full items-center justify-between gap-3">
          <BigRoundButton label="인원 줄이기" disabled={players <= MIN_PLAYERS} onClick={() => change(-1)}>
            −
          </BigRoundButton>
          <div className="flex flex-col items-center">
            <span className="font-display neon-pink text-[5.5rem] leading-none tabular-nums">{players}</span>
            <span className="mt-1 text-xl font-bold text-white/80">명</span>
          </div>
          <BigRoundButton label="인원 늘리기" disabled={players >= MAX_PLAYERS} onClick={() => change(1)}>
            +
          </BigRoundButton>
        </div>
        <div className="flex max-w-[18rem] flex-wrap justify-center gap-1.5 text-2xl" aria-hidden="true">
          {Array.from({ length: players }).map((_, i) => (
            <span key={i} className="animate-[rb-rise_.25s_ease-out_both]">
              🙋
            </span>
          ))}
        </div>
        <p className="text-sm text-white/50">
          최소 {MIN_PLAYERS}명 · 최대 {MAX_PLAYERS}명
        </p>
      </section>

      <button
        type="button"
        onClick={onStart}
        className="font-display h-20 w-full rounded-3xl bg-[#ff3d9a] text-3xl text-[#1a0010] shadow-[0_0_0_3px_#ff9cca_inset,0_10px_0_#a3004f,0_0_40px_rgba(255,61,154,.55)] transition-all duration-100 active:translate-y-[8px] active:shadow-[0_0_0_3px_#ff9cca_inset,0_2px_0_#a3004f,0_0_24px_rgba(255,61,154,.4)]"
      >
        게임 시작 🔥
      </button>
    </main>
  )
}

function BigRoundButton({ children, onClick, disabled, label }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="font-display grid h-28 w-28 shrink-0 place-items-center rounded-full border-4 border-[#3ff3ff] bg-[#3ff3ff]/10 text-[4.5rem] leading-none text-[#3ff3ff] shadow-[0_0_24px_rgba(63,243,255,.45),inset_0_0_18px_rgba(63,243,255,.25)] transition-transform duration-100 active:scale-90 disabled:border-white/15 disabled:bg-transparent disabled:text-white/20 disabled:shadow-none"
    >
      {children}
    </button>
  )
}

/* =========================================================================
 * 2. 메인 게임 화면
 * ========================================================================= */
function PlayScreen({ players, currentTurn, phase, beatMs, onPay, onQuit }) {
  const busy = phase !== 'idle'
  const remaining = players - currentTurn + 1

  const lcd = {
    idle: { top: `${currentTurn}번 손님`, main: '카드를 긁어주세요' },
    processing: { top: '통신 중', main: '승인 중' },
    pass: { top: '잔액 부족', main: '승인 거절 · 통과!' },
    boom: { top: '결제 완료', main: '승인되었습니다' },
  }[phase]

  return (
    <>
    <main
      className={`relative mx-auto flex h-full max-w-md flex-col px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))] ${
        phase === 'boom' ? 'motion-safe-only animate-[rb-shake_.45s_linear_3]' : ''
      }`}
    >
      {/* 상단: 나가기 + 차례 */}
      <div className="flex h-12 items-center pr-14">
        <button
          type="button"
          onClick={onQuit}
          disabled={busy}
          className="rounded-full border border-white/15 px-4 py-2 text-sm font-bold text-white/70 active:scale-95 disabled:opacity-30"
        >
          ← 처음으로
        </button>
      </div>

      <div className="mt-3 text-center">
        <p className="font-display text-[2.4rem] leading-tight">
          <span className="neon-pink tabular-nums">{currentTurn}번</span> 차례
        </p>
        <p className="mt-1 text-base text-white/65">
          폰을 <b className="text-white">{currentTurn}번</b>에게 넘기세요 · 남은 사람 <b className="text-white tabular-nums">{remaining}</b>명
        </p>
      </div>

      {/* 참가자 좌석 표시 */}
      <ol className="mt-4 flex flex-wrap justify-center gap-2" aria-label="진행 상황">
        {Array.from({ length: players }).map((_, i) => {
          const n = i + 1
          const done = n < currentTurn
          const now = n === currentTurn
          return (
            <li
              key={n}
              className={`grid h-10 w-10 place-items-center rounded-full text-base font-extrabold tabular-nums transition ${
                done
                  ? 'bg-[#4dff9b] text-[#002611]'
                  : now
                    ? 'border-2 border-[#ff3d9a] bg-[#ff3d9a]/15 text-[#ff3d9a] shadow-[0_0_14px_rgba(255,61,154,.7)]'
                    : 'border border-white/20 text-white/40'
              }`}
            >
              {done ? '✓' : n}
            </li>
          )
        })}
      </ol>

      {/* 카드 단말기 */}
      <div className="my-auto flex justify-center py-4">
        <div
          className="motion-safe-only relative w-64 rounded-[2.2rem] border border-white/10 bg-gradient-to-b from-[#2a2438] to-[#141019] p-4 pt-9"
          style={{ animation: phase === 'boom' ? 'none' : `rb-beat ${beatMs}ms ease-in-out infinite` }}
        >
          {/* 영수증 출력구 */}
          <div className="absolute left-1/2 top-3 h-2 w-40 -translate-x-1/2 rounded-full bg-black/80 shadow-[inset_0_1px_2px_rgba(0,0,0,.9)]" />
          {/* LCD */}
          <div
            className={`font-receipt rounded-2xl border-2 p-4 text-center transition-colors ${
              phase === 'pass'
                ? 'border-[#4dff9b] bg-[#06301a]'
                : phase === 'boom'
                  ? 'border-red-400 bg-red-700'
                  : 'border-[#1f4d33] bg-[#0b2416]'
            }`}
          >
            <p className="lcd text-xs font-bold tracking-widest opacity-80">{lcd.top}</p>
            <p className="lcd mt-1 text-xl font-bold">
              {lcd.main}
              {phase === 'processing' && <span className="animate-[rb-blink_.5s_steps(2)_infinite]">...</span>}
            </p>
          </div>
          {/* 카드 슬롯 + 긁는 카드 */}
          <div className="relative mt-4 h-10 overflow-hidden rounded-lg bg-black/70 shadow-[inset_0_2px_6px_rgba(0,0,0,.9)]">
            {phase === 'processing' && (
              <div className="absolute inset-y-1 left-1/2 w-20 -translate-x-1/2 animate-[rb-swipe_.6s_ease-in_both] rounded-md bg-gradient-to-br from-[#ffd166] to-[#ff3d9a]" />
            )}
          </div>
          {/* 키패드 */}
          <div className="mt-4 grid grid-cols-3 gap-2" aria-hidden="true">
            {['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#'].map((k) => (
              <span key={k} className="font-receipt grid h-8 place-items-center rounded-lg bg-white/[.07] text-sm text-white/40">
                {k}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* 결제 버튼 */}
      <button
        type="button"
        onClick={onPay}
        disabled={busy}
        className="font-display h-28 w-full shrink-0 rounded-[2rem] bg-[#3ff3ff] text-[2.4rem] text-[#001a1c] shadow-[0_0_0_3px_#b8fbff_inset,0_12px_0_#008a94,0_0_50px_rgba(63,243,255,.5)] transition-all duration-100 active:translate-y-[10px] active:shadow-[0_0_0_3px_#b8fbff_inset,0_2px_0_#008a94,0_0_24px_rgba(63,243,255,.35)] disabled:translate-y-[10px] disabled:shadow-[0_0_0_3px_#b8fbff_inset,0_2px_0_#008a94] disabled:brightness-75"
      >
        💳 카드 긁기
      </button>
    </main>

      {/* 통과 팝업 */}
      {phase === 'pass' && (
        <div className="pointer-events-none fixed left-1/2 top-1/2 z-30 animate-[rb-pop_.5s_ease-out_both] text-center">
          <p className="font-display neon-green whitespace-nowrap text-[5.5rem] leading-none">통과!</p>
          <p className="mt-2 text-xl font-bold text-[#4dff9b]">휴… 살았다 😮‍💨</p>
        </div>
      )}

      {/* 폭탄: 전체 화면 붉은 플래시 */}
      {phase === 'boom' && (
        <div className="pointer-events-none fixed inset-0 z-30 grid place-items-center">
          <div className="absolute inset-0 animate-[rb-flash_1.2s_linear_both] bg-red-500" />
          <p className="font-display relative animate-[rb-pop_1.6s_ease-out_both] text-[6rem] leading-none text-white drop-shadow-[0_0_30px_rgba(0,0,0,.6)]">
            💥 승인!
          </p>
        </div>
      )}
    </>
  )
}

/* =========================================================================
 * 3. 결과 화면
 * ========================================================================= */
function ResultScreen({ players, bombTurn, receipt, onRetry, onHome }) {
  const at = receipt?.at ?? new Date()
  const stamp = `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, '0')}-${String(at.getDate()).padStart(2, '0')} ${String(
    at.getHours(),
  ).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`

  return (
    <main className="relative flex h-full flex-col bg-[radial-gradient(ellipse_at_50%_0%,#ff4d6d_0%,#d4003c_45%,#5c0020_100%)]">
      <div className="mx-auto flex h-full w-full max-w-md flex-col px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))]">
        <header className="mt-10 text-center">
          <p className="font-display motion-safe-only animate-[rb-glow_1s_ease-in-out_infinite] text-[4.2rem] leading-none text-[#fff36b] drop-shadow-[0_0_20px_rgba(255,243,107,.7)]">
            당첨!
          </p>
          <p className="font-display mt-3 text-[1.9rem] leading-tight">카드를 준비하세요 💳</p>
          <p className="mt-2 text-lg font-bold text-white/90">
            <span className="rounded-full bg-black/30 px-3 py-1 tabular-nums">{bombTurn}번</span> 님이 오늘의 결제 요정 🧚
          </p>
        </header>

        {/* 출력구 + 영수증 */}
        <div className="relative mt-6 min-h-0 flex-1">
          <div className="relative z-10 mx-auto h-4 w-[88%] rounded-full bg-[#1a0008] shadow-[0_4px_10px_rgba(0,0,0,.6)]" />
          <div className="-mt-2 mx-auto h-[calc(100%-0.5rem)] w-[80%] overflow-y-auto overflow-x-hidden">
            <div className="zigzag-bottom motion-safe-only animate-[rb-print_1.8s_steps(18,end)_both] bg-[#f6f3ea] text-[#1b1b1b] shadow-[0_12px_30px_rgba(0,0,0,.4)]">
              <div className="font-receipt px-4 pb-5 pt-6 text-[13px] leading-relaxed">
                <p className="text-center text-base font-bold">** 영수증 폭탄 식당 **</p>
                <p className="text-center text-xs text-black/60">사업자 000-00-00000 · 서울시 밥값구</p>
                <p className="mt-2 text-xs text-black/70">
                  {stamp} · 승인번호 {receipt?.no}
                </p>
                <Dashed />
                {receipt?.items.map((it) => (
                  <div key={it.name} className="flex justify-between gap-2">
                    <span className="truncate">
                      {it.name} ×{it.qty}
                    </span>
                    <span className="tabular-nums">{won(it.price)}</span>
                  </div>
                ))}
                <Dashed />
                <div className="flex justify-between text-base font-bold">
                  <span>합계</span>
                  <span className="tabular-nums">{won(receipt?.total ?? 0)}원</span>
                </div>
                <div className="flex justify-between text-xs text-black/60">
                  <span>인원</span>
                  <span>{players}명 (1/N 없음)</span>
                </div>
                <Dashed />
                <p>결제자 : {bombTurn}번 손님</p>
                <p>카드 : ****-****-****-{String(1000 + bombTurn * 777).slice(-4)}</p>
                <p className="mt-1 text-center font-bold">[ 승 인 완 료 ]</p>
                <div className="barcode mx-auto mt-3 h-10 w-[85%]" />
                <p className="mt-2 text-center text-xs text-black/60">잘 먹었습니다! 또 오세요 🙏</p>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex shrink-0 flex-col gap-3">
          <button
            type="button"
            onClick={onRetry}
            className="font-display h-20 w-full rounded-3xl bg-[#fff36b] text-3xl text-[#3a0012] shadow-[0_10px_0_#b8a800,0_0_36px_rgba(255,243,107,.5)] transition-all duration-100 active:translate-y-[8px] active:shadow-[0_2px_0_#b8a800]"
          >
            다시 하기 🔄
          </button>
          <button
            type="button"
            onClick={onHome}
            className="h-14 w-full rounded-2xl border-2 border-white/40 text-lg font-bold text-white active:scale-[.98]"
          >
            인원 바꾸기
          </button>
        </div>
      </div>
    </main>
  )
}

function Dashed() {
  return <div className="my-2 border-t-2 border-dashed border-black/30" />
}
