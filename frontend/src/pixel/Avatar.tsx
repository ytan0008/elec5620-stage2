import { useEffect, useMemo, useState } from 'react'

export type Persona = 'witch' | 'boy'
export type AvatarMood = 'idle' | 'talking' | 'listening' | 'thinking' | 'happy'

const W = 32
const H = 40

/* Each sprite row is the LEFT half (16 px); the right half is mirrored, with
   highlight letters swapped for shade letters so light comes from the left. */
const SHADE: Record<string, string> = { L: 'h', n: 'N', U: 'u' }
function mirror(rows: string[]): string[] {
  return rows.map(left => {
    const half = left.padEnd(16, '.').slice(0, 16)
    const right = half.split('').reverse().map(ch => SHADE[ch] ?? ch).join('')
    return half + right
  })
}
type Overlay = [row: number, col: number, pixels: string]
function paint(base: string[], overlays: Overlay[]): string[] {
  const grid = base.map(row => row.split(''))
  for (const [row, col, pixels] of overlays) {
    pixels.split('').forEach((ch, i) => { if (ch !== ' ' && grid[row] && col + i < W) grid[row][col + i] = ch })
  }
  return grid.map(row => row.join(''))
}

const PALETTE: Record<string, string> = {
  K: '#140c2e', H: '#5b2a9e', h: '#3a1a73', L: '#8a55e0', B: '#ffcc4d', b: '#d9931c', Y: '#fff27a',
  R: '#ff7ad9', r: '#c94bb0', S: '#ffdcc6', s: '#f2b49b', E: '#2b1a4d', W: '#ffffff', P: '#ff9fb8', M: '#9e2b4f', T: '#ff5f7e',
  O: '#2d1f6e', o: '#1d1450', C: '#3ef0ff', G: '#8b5a2b', g: '#5e3a1a', X: '#3ef0ff', x: '#c9fdff',
  N: '#283079', n: '#5160e0', D: '#3ef0ff', d: '#1fa8b8', U: '#ff8a3d', u: '#c9561f', Q: '#3b4a9e', q: '#28336f', Z: '#b8ff5c',
}

const WITCH = paint(mirror([
  '', '', '..............KL', '.............KLH', '............KLHH', '...........KLHHH', '..........KLHHHH', '.........KLHHHHH',
  '........KLHHHHHH', '.......KBBBBBBBB', '.......KBBBBBBYY', '....KKKKHHHHHHHH', '..KKLLLHHHHHHHHH', '.KhhhhhhhhhhhhhH', '..KKKKKRRRRRRRRR',
  '....KRRRRRRRRRRR', '...KRRRRRSSSSSSS', '...KRRRRSSSSSSSS', '...KRRRSSSSSSSSS', '...KRRRSSSSSSSSS', '...KRRRSSSSSSSSS', '...KRRRSSSSSSSSS',
  '...KRRRSSSSSSSSS', '...KRRRRSSSSSSSS', '...KRRRRRSSSSSSS', '...KRRRRRRKSSSSS', '..KRRRRRRRRKKKSS', '..KRRRRRRRKOOOCC', '.KRRRRRRKOOOOOOC',
  '.KRRRRRKOOOOOOOO', '.KRRRRKOOOOOOOOO', '..KRRKOOOOOOOOOO', '...KKOOOOOOOOOOO', '...KOOOOOOOOOOOO', '..KOOOOOOOOOOOOO', '..KOOOOOOOOOOOOO',
  '.KOOOOOOOOOOOOOO', '.KooooooooooooOO', '..KKKKKKKKKKKKKK', '',
]), [
  [0, 17, 'KK'], [1, 15, 'KHhK'], [1, 19, 'K'], [0, 19, 'K'],
  [31, 14, 'YY'], [32, 13, 'YYYY'], [33, 14, 'YY'],
  // staff with crystal orb
  ...Array.from({ length: 25 }, (_, i) => [12 + i, 27, 'Gg'] as Overlay),
  [6, 27, 'KK'], [7, 26, 'KxXK'], [8, 25, 'KxxXXK'], [9, 25, 'KxXXdK'], [10, 25, 'KXXddK'], [11, 26, 'KddK'], [12, 27, 'KK'],
  [28, 25, 'SSK'], [29, 25, 'SSK'],
  [6, 15, 'Y'], [5, 15, 'Y'], [6, 14, 'Y'], [6, 16, 'Y'], [7, 15, 'Y'],
  [16, 7, 'RRRRRRRRRRRRRRRRRR'], [17, 8, 'RR RRR    RRR RR'],
])

const BOY = paint(mirror([
  '', '', '', '........K...K...', '.......KnK.KnK.K', '......KnNKKnNKKn', '.....KnNNNnNNNnN', '....KnNNNNNNNNNN', '...KnNNNNNNNNNNN',
  '...KNNNNNNNNNNNN', '..KDNNNNNNNNNNNN', '..KDNNNNSNNNNSNN', '..KDNNNSSSNNSSSS', '.KDDNNSSSSSSSSSS', '.KDDDNSSSSSSSSSS', '.KDDDNSSSSSSSSSS',
  '.KDDDNSSSSSSSSSS', '.KDDDNSSSSSSSSSS', '..KDDNSSSSSSSSSS', '..KKKNSSSSSSSSSS', '....KSSSSSSSSSSS', '.....KSSSSSSSSSS', '......KKSSSSSSSS',
  '........KKKKKKSS', '......KUUUUUUKSS', '.....KUUUUUUUUKC', '....KUUUUUUUUUUC', '...KUUUUUUUUUUUU', '..KUUUUUUUUUUUUU', '..KUUUKUUUUUUUUU',
  '..KUUUKUUUUUUUUU', '..KUUUKUUUUUUUUU', '..KSSSKUUUUUUUUU', '..KKKKKUUUUUUUUU', '......KuuuuuuuuU', '......KUUUUUUUUU', '......KKKKKKKKKK',
  '.......KQQQQQKQQ', '.......KqqqqqK..', '.......KKKKKKK..',
]), [
  [26, 15, 'ZZ'], [27, 14, 'Z  Z'],
])

/* Faces are drawn on top so they can blink and talk. */
type Face = { eyes: [number, number][]; eyeRows: number; blush: [number, number][]; mouth: [number, number] }
const FACES: Record<Persona, Face> = {
  witch: { eyes: [[19, 10], [19, 20]], eyeRows: 3, blush: [[22, 8], [22, 22]], mouth: [24, 15] },
  boy: { eyes: [[15, 9], [15, 21]], eyeRows: 3, blush: [[18, 7], [18, 23]], mouth: [20, 15] },
}

function faceOverlays(persona: Persona, blink: boolean, mouthOpen: number, mood: AvatarMood): Overlay[] {
  const face = FACES[persona]
  const out: Overlay[] = []
  for (const [row, col] of face.eyes) {
    if (blink) out.push([row + face.eyeRows - 1, col, 'EE'])
    else if (mood === 'happy') { out.push([row + 1, col, 'EE']); out.push([row, col, '  ']) }
    else {
      const look = mood === 'thinking' ? 0 : 0
      out.push([row, col + look, 'WE'], [row + 1, col + look, 'EE'], [row + 2, col + look, 'EE'])
    }
  }
  for (const [row, col] of face.blush) out.push([row, col, 'PP'])
  const [mr, mc] = face.mouth
  if (mouthOpen === 2) out.push([mr - 1, mc - 1, 'KMMK'], [mr, mc - 1, 'MTTM'], [mr + 1, mc, 'MM'])
  else if (mouthOpen === 1) out.push([mr, mc - 1, 'KMMK'], [mr + 1, mc, 'TT'])
  else if (mood === 'happy' || mood === 'idle') out.push([mr, mc - 1, 'M  M'], [mr + 1, mc, 'MM'])
  else out.push([mr, mc, 'MM'])
  return out
}

function Sprite({ rows }: { rows: string[] }) {
  const rects = useMemo(() => {
    const out: { x: number; y: number; w: number; c: string }[] = []
    rows.forEach((row, y) => {
      let x = 0
      while (x < row.length) {
        const ch = row[x]
        if (ch === '.' || ch === ' ' || !PALETTE[ch]) { x++; continue }
        let end = x + 1
        while (end < row.length && row[end] === ch) end++
        out.push({ x, y, w: end - x, c: PALETTE[ch] })
        x = end
      }
    })
    return out
  }, [rows])
  return <>{rects.map((r, i) => <rect key={i} x={r.x} y={r.y} width={r.w} height={1} fill={r.c} />)}</>
}

export function PixelAvatar({ persona, mood = 'idle', size = 160, className = '', label }: { persona: Persona; mood?: AvatarMood; size?: number; className?: string; label?: string }) {
  const [blink, setBlink] = useState(false)
  const [mouth, setMouth] = useState(0)
  useEffect(() => {
    let alive = true
    const loop = () => {
      const wait = 2200 + Math.random() * 3200
      window.setTimeout(() => { if (!alive) return; setBlink(true); window.setTimeout(() => { if (alive) { setBlink(false); loop() } }, 140) }, wait)
    }
    loop()
    return () => { alive = false }
  }, [])
  useEffect(() => {
    if (mood !== 'talking') { setMouth(0); return }
    const id = window.setInterval(() => setMouth(Math.random() < .2 ? 0 : Math.random() < .5 ? 1 : 2), 120)
    return () => window.clearInterval(id)
  }, [mood])
  const base = persona === 'boy' ? BOY : WITCH
  const rows = useMemo(() => paint(base, faceOverlays(persona, blink, mouth, mood)), [base, persona, blink, mouth, mood])
  const name = persona === 'boy' ? 'Kai' : 'Luna'
  return <div className={`relative inline-block ${className}`} style={{ width: size, height: size * H / W }} role="img" aria-label={label || `${name}, pixel ${persona === 'boy' ? 'boy' : 'witch'} AI tutor (${mood})`}>
    {mood === 'listening' && <span className="absolute inset-[12%] rounded-full border-4 border-cyan" style={{ animation: 'ring 1.2s steps(6) infinite' }} />}
    <svg viewBox={`0 0 ${W} ${H}`} width={size} height={size * H / W} shapeRendering="crispEdges" className={`relative ${mood === 'talking' ? '' : 'anim-bob'} anim-glow`}>
      <Sprite rows={rows} />
    </svg>
    {mood === 'talking' && <Sparkles color={persona === 'boy' ? '#ff8a3d' : '#3ef0ff'} />}
    {mood === 'thinking' && <span className="absolute -top-1 right-0 bg-moon px-2 py-0.5 font-arcade text-[10px] text-night" style={{ boxShadow: '0 0 0 3px #140c2e' }}>
      <span className="inline-block animate-pulse">. . .</span>
    </span>}
    {mood === 'listening' && <span className="absolute -right-1 top-1/3 flex h-8 items-end gap-[3px]" aria-hidden>
      {[0, 1, 2, 3].map(i => <span key={i} className="eq-bar block w-[5px] bg-cyan" style={{ animationDelay: `${i * .15}s` }} />)}
    </span>}
  </div>
}

function Sparkles({ color }: { color: string }) {
  return <span aria-hidden className="pointer-events-none absolute inset-0">
    {[[18, 20], [78, 14], [86, 46], [10, 52], [60, 4]].map(([x, y], i) =>
      <span key={i} className="absolute block h-2 w-2" style={{ left: `${x}%`, top: `${y}%`, background: i % 2 ? color : '#ffd34d', animation: `sparkle 1.4s steps(6) ${i * .25}s infinite` }} />)}
  </span>
}

export function personaName(persona: Persona) { return persona === 'boy' ? 'Kai' : 'Luna' }
