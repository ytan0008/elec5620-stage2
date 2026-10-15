export type User={id:number;email:string;name:string;role:'learner'|'instructor'}
export type Profile={exam:'IELTS'|'TOEFL';proficiency:string;target_score:number;exam_date:string;weekly_hours:number;priority_skills:string[]}
export type Result={id:number;kind:string;state:string;source_mode:string;issues:string[];payload?:Record<string,any>;confidence?:Record<string,number>;message?:string;created_at:string}
export type Plan={id:number;version:number;kind:string;status:string;content?:Record<string,any>;created_at:string}
export type Practice={id:number;skill:string;prompt:{title:string;text:string;mode:string;duration_seconds:number}}
export type Mock={id:number;exam:string;status:string;reduced_length:boolean;sections:Record<string,{title:string;text:string;duration_seconds:number}>;answers:Record<string,string>;result:Result|null}
export type Event={id:number;workflow:string;agent:string;phase:string;detail:Record<string,any>;mode:string;duration_ms:number;created_at:string}

export async function request<T=any>(path:string, options:RequestInit={}):Promise<T>{
  const token=localStorage.getItem('certifyai_token')
  const headers:Record<string,string>={...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...(token?{Authorization:`Bearer ${token}`}:{})}
  const response=await fetch(`/api${path}`,{...options,headers:{...headers,...options.headers}})
  if(!response.ok){let detail='Request failed';try{const body=await response.json();detail=typeof body.detail==='string'?body.detail:JSON.stringify(body.detail)}catch{}throw new Error(detail)}
  return response.json()
}
export function post<T=any>(path:string,data?:unknown):Promise<T>{return request<T>(path,{method:'POST',body:data===undefined?undefined:JSON.stringify(data)})}
export function put<T=any>(path:string,data:unknown):Promise<T>{return request<T>(path,{method:'PUT',body:JSON.stringify(data)})}
