import { useEffect, useMemo, useRef, type ReactElement } from 'react'

/* Generic pixel-art renderer: rows of palette letters, merged into horizontal runs. */
export function PixelArt({ rows, palette, scale = 4, className = '', style }: { rows: string[]; palette: Record<string, string>; scale?: number; className?: string; style?: React.CSSProperties }) {
  const width = Math.max(...rows.map(row => row.length))
  const rects = useMemo(() => rows.flatMap((row, y) => {
    const out: ReactElement[] = []
    let x = 0
    while (x < row.length) {
      const ch = row[x]
      if (!palette[ch]) { x++; continue }
      let end = x + 1
      while (end < row.length && row[end] === ch) end++
      out.push(<rect key={`${x}-${y}`} x={x} y={y} width={end - x} height={1} fill={palette[ch]} />)
      x = end
    }
    return out
  }), [rows, palette])
  return <svg aria-hidden viewBox={`0 0 ${width} ${rows.length}`} width={width * scale} height={rows.length * scale} shapeRendering="crispEdges" className={className} style={style}>{rects}</svg>
}

const MOON = [
  '.......MMMMMM.......', '.....MMMMMMMMMM.....', '....MMMMMMMMMMMM....', '...MMMMMcMMMMMMMM...', '..MMMMMcccMMMMMMMM..', '..MMMMMMcMMMMMmMMM..',
  '.MMMMMMMMMMMMMMMMMM.', '.MMMMMMMMMMMMMMMMMM.', '.MMMmMMMMMMMMMMMMMM.', '.MMmmmMMMMMMMMcMMMM.', '.MMMmMMMMMMMMcccMMM.', '.MMMMMMMMMMMMMcMMMM.',
  '..MMMMMMMMMMMMMMMM..', '..MMMMMMMMMmMMMMMM..', '...MMMMMMMmmmMMMM...', '....MMMMMMMmMMMM....', '.....MMMMMMMMMM.....', '.......MMMMMM.......',
]
const MOON_P = { M: '#ffe9b8', m: '#f3c97a', c: '#e7b864' }

const ISLAND = [
  '......gggggggggg..........', '....ggGGGGGGGGGGgg........', '..ggGGGGGtGGGGGGGGgg......', '.gGGGGGGtttGGGGGGGGGGg....', 'gGGGGGGGGTGGGGGGGGGGGGg...',
  'dddddddddddddddddddddddd..', '.ddDDDdddddDDDddddDDdddd..', '..ddddDDDdddddddDDddddd...', '...dddddddDDDDdddddddd....', '....ddddddddddddddddd.....',
  '.....dddDDddddddddd.......', '......dddddddDDdd.........', '.......ddddddddd..........', '........dddddd............', '.........dddd.............',
  '..........dd.............', '..........d..............',
]
const ISLAND_P = { g: '#5ee08a', G: '#3fbf6e', t: '#2d8f55', T: '#7a4b2a', d: '#6b4a8f', D: '#4b3270' }

const WHALE = [
  '..............................ww....', '.............................wWWw...', '......bbbbbbbbbbbb..........wWWw....', '...bbbBBBBBBBBBBBBbbb......wWw.....',
  '.bbBBBBBBBBBBBBBBBBBBbbb..bbw......', 'bBBeBBBBBBBBBBBBBBBBBBBbbbBb.......', 'bBBBBBBBBBBBBBBBBBBBBBBBBBbb.......', '.bLLLLLLLLLLLLLLLBBBBBBBbb.........',
  '..bLLLLLLLLLLLLLLLLLBbb...........', '....bbbbbbbbbbbbbbbb..............', '..........bBb.......................', '...........b........................',
]
const WHALE_P = { b: '#2a1d5c', B: '#4b2fa8', L: '#9b8cff', e: '#ffd34d', w: '#3ef0ff', W: '#c9fdff' }

const CLOUD = ['....cccc......', '..cccccccc.ccc.', '.cccccccccccccc', 'cccccccccccccccc', '.CCCCCCCCCCCCCC.']
const CLOUD_P = { c: 'rgba(244,236,255,.18)', C: 'rgba(185,176,224,.12)' }

const PYRAMID = ['.......p.......', '......pPp......', '.....pPPPp.....', '....pPPePPp....', '...pPPPPPPPp...', '..pPPPPPPPPPp..', '.pPPPPPPPPPPPp.', 'pPPPPPPPPPPPPPp']
const PYRAMID_P = { p: '#ff4fd8', P: '#a03ba8', e: '#3ef0ff' }

function Stars() {
  const ref = useRef<HTMLCanvasElement | null>(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let stars: { x: number; y: number; s: number; p: number; c: string }[] = []
    let shooting: { x: number; y: number; life: number } | null = null
    const colors = ['#f4ecff', '#3ef0ff', '#ff4fd8', '#ffd34d']
    const resize = () => {
      canvas.width = Math.ceil(window.innerWidth / 3)
      canvas.height = Math.ceil(window.innerHeight / 3)
      stars = Array.from({ length: Math.round(canvas.width * canvas.height / 260) }, () => ({ x: Math.random() * canvas.width | 0, y: Math.random() * canvas.height * .82 | 0, s: Math.random() < .12 ? 2 : 1, p: Math.random() * Math.PI * 2, c: colors[Math.random() < .8 ? 0 : 1 + (Math.random() * 3 | 0)] }))
    }
    resize()
    window.addEventListener('resize', resize)
    let frame = 0, raf = 0, last = 0
    const draw = (t: number) => {
      raf = requestAnimationFrame(draw)
      if (t - last < 66 || document.hidden) return
      last = t
      frame++
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      for (const star of stars) {
        const a = .35 + .65 * Math.abs(Math.sin(star.p + frame * .05))
        ctx.globalAlpha = reduced ? .8 : a
        ctx.fillStyle = star.c
        ctx.fillRect(star.x, star.y, star.s, star.s)
      }
      ctx.globalAlpha = 1
      if (!reduced) {
        if (!shooting && Math.random() < .006) shooting = { x: Math.random() * canvas.width * .7 + canvas.width * .2, y: Math.random() * canvas.height * .3, life: 0 }
        if (shooting) {
          for (let i = 0; i < 8; i++) {
            ctx.globalAlpha = 1 - i / 8
            ctx.fillStyle = i < 2 ? '#ffffff' : '#3ef0ff'
            ctx.fillRect(shooting.x + i * 2, shooting.y - i, 1, 1)
          }
          ctx.globalAlpha = 1
          shooting.x -= 4; shooting.y += 2; shooting.life++
          if (shooting.life > 30) shooting = null
        }
      }
    }
    raf = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize) }
  }, [])
  return <canvas ref={ref} aria-hidden className="absolute inset-0 h-full w-full" style={{ imageRendering: 'pixelated' }} />
}

export default function Scene() {
  return <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" style={{ background: 'linear-gradient(180deg, #07051a 0%, #120c38 38%, #2a1458 66%, #5a1a6e 84%, #ff4fd8 130%)' }}>
    <Stars />
    <div className="absolute right-[6%] top-[7%] anim-glow" style={{ filter: 'drop-shadow(0 0 28px rgba(255,211,77,.55))' }}><PixelArt rows={MOON} palette={MOON_P} scale={7} /></div>
    <div className="absolute left-0 top-[16%] opacity-80" style={{ animation: 'drift 140s linear infinite' }}><PixelArt rows={WHALE} palette={WHALE_P} scale={5} /></div>
    <div className="absolute left-0 top-[42%] opacity-70" style={{ animation: 'drift 95s linear -40s infinite' }}><PixelArt rows={CLOUD} palette={CLOUD_P} scale={8} /></div>
    <div className="absolute left-0 top-[8%] opacity-60" style={{ animation: 'drift 120s linear -80s infinite' }}><PixelArt rows={CLOUD} palette={CLOUD_P} scale={6} /></div>
    <div className="absolute left-[3%] top-[55%] anim-float" style={{ animationDelay: '-2s' }}><PixelArt rows={ISLAND} palette={ISLAND_P} scale={5} /></div>
    <div className="absolute right-[12%] top-[48%] anim-float opacity-90" style={{ animationDelay: '-4.5s' }}><PixelArt rows={ISLAND} palette={ISLAND_P} scale={3} /></div>
    <div className="absolute left-[44%] top-[30%] anim-float opacity-50" style={{ animationDuration: '11s' }}><PixelArt rows={PYRAMID} palette={PYRAMID_P} scale={4} /></div>
    <div className="absolute inset-x-0 bottom-0 h-[26vh] opacity-60" style={{
      background: 'linear-gradient(transparent 0, rgba(255,79,216,.12) 100%), repeating-linear-gradient(90deg, rgba(62,240,255,.45) 0 2px, transparent 2px 48px), repeating-linear-gradient(0deg, rgba(62,240,255,.45) 0 2px, transparent 2px 48px)',
      transform: 'perspective(240px) rotateX(58deg)', transformOrigin: 'bottom', animation: 'grid-move 2.4s linear infinite',
      maskImage: 'linear-gradient(transparent, black 70%)', WebkitMaskImage: 'linear-gradient(transparent, black 70%)',
    }} />
  </div>
}
