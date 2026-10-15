import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Network } from 'lucide-react'
import { request } from './api'

type Node={id:string;label:string;type:'goal'|'skill'|'concept';skill:string|null;score:number|null;priority:boolean;resource_count?:number}
type Edge={source:string;target:string;relation:string}
type Graph={nodes:Node[];edges:Edge[];score_note:string;sample_count:number;source_mode:string}
const order=['listening','reading','writing','speaking']
const centers=[125,375,625,875]

export default function KnowledgeGraphPage(){
  const [graph,setGraph]=useState<Graph|null>(null)
  const [selected,setSelected]=useState<Node|null>(null)
  const [error,setError]=useState('')
  useEffect(()=>{request<Graph>('/knowledge-graph').then(setGraph).catch(e=>setError(e.message))},[])
  if(error)return <div className="panel panel-hot p-6 font-read text-rose">{error}</div>
  if(!graph)return <div className="panel p-6 font-pixel">Mapping your knowledge constellation…</div>
  const position=(node:Node):[number,number]=>{
    if(node.type==='goal')return [500,65]
    const column=order.indexOf(node.skill||'')
    if(node.type==='skill')return [centers[column],230]
    const siblings=graph.nodes.filter(item=>item.type==='concept'&&item.skill===node.skill)
    return [centers[column],385+siblings.findIndex(item=>item.id===node.id)*78]
  }
  const byId=Object.fromEntries(graph.nodes.map(node=>[node.id,node]))
  const active=selected||graph.nodes[0]
  return <div className="space-y-6">
    <div className="flex items-center gap-3"><div className="bg-plum p-3 text-cyan" style={{boxShadow:'0 0 0 3px #6b52d6'}}><Network/></div><div><span className="eyebrow">Your learning map</span><h1 className="heading title-glow mt-2 text-3xl">Knowledge graph</h1></div></div>
    <p className="max-w-3xl font-read text-mist">Explore how the four IELTS/TOEFL skills and twelve study concepts connect to your target. Priority skills are highlighted; scores appear only after verified practice.</p>
    <div className="grid gap-5 xl:grid-cols-[1fr_290px]">
      <div className="panel overflow-x-auto p-3 md:p-5"><svg viewBox="0 0 1000 610" className="min-w-[720px] w-full" role="img" aria-label="Interactive graph of examination goal, skills and study concepts">
        {graph.edges.map(edge=>{const a=position(byId[edge.source]),b=position(byId[edge.target]);return <line key={`${edge.source}-${edge.target}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#6b52d6" strokeWidth="3" strokeDasharray="6 4"/>})}
        {graph.nodes.map(node=>{const [x,y]=position(node),isActive=active.id===node.id;return <g key={node.id} role="button" tabIndex={0} aria-label={`Show ${node.label}`} onClick={()=>setSelected(node)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setSelected(node)}}} className="cursor-pointer"><rect x={x-(node.type==='goal'?115:node.type==='skill'?86:92)} y={y-25} width={node.type==='goal'?230:node.type==='skill'?172:184} height="50" rx="0" fill={isActive?'#ff4fd8':node.priority?'#2a1d5c':'#15113a'} stroke={isActive?'#ffd34d':node.priority?'#3ef0ff':'#3a2b7e'} strokeWidth="4"/><text x={x} y={y+5} textAnchor="middle" fill={isActive?'#0d0a24':'#f4ecff'} fontFamily="Pixelify Sans" fontSize={node.type==='concept'?'15':'18'} fontWeight="700">{node.label.length>23?node.label.slice(0,21)+'…':node.label}</text></g>})}
      </svg></div>
      <aside className="panel panel-cyan h-fit p-6"><span className="eyebrow">Selected concept</span><h2 className="heading mt-2 text-xl">{active.label}</h2><p className="mt-3 font-read text-sm text-mist">{active.type==='goal'?'Your self-reported examination target.':active.type==='skill'?'One of the four assessed language skills.':'A learning concept linked to its parent skill.'}</p><div className="mt-5 space-y-2 font-pixel"><p><strong>Priority:</strong> {active.priority?'Yes':'No'}</p><p><strong>Verified score:</strong> {active.score??'Insufficient data'}</p><p><strong>Matching lessons:</strong> {active.resource_count??'—'}</p></div>{active.skill&&<div className="mt-6 flex flex-col gap-2"><Link to={`/practice/${active.skill}`} className="btn-primary">Practise {active.skill}<ArrowRight size={16}/></Link><Link to="/materials" className="btn-secondary">Explore materials</Link></div>}</aside>
    </div>
    <p className="font-read text-sm text-fog">{graph.score_note} {graph.sample_count} verified result(s) currently contribute to the skill overlay. The concept links are a curated learning taxonomy, not an inferred mastery model.</p>
  </div>
}
