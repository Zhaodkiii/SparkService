import http from '../http';
export interface SupportPage<T> { results:T[]; next_cursor:string|null }
export interface Ticket { id:string; number:string; title:string; kind:string; status:string; revision:number; owner_id:number; assignee_id:number|null; assignee:string; contact:string; source:string; priority:string; tags:string[]; environment:Record<string,string>; allowed_actions:string[]; public_sequence:number; user_unread:boolean; related_type:string; related_id:string|null; created_at:string; last_public_activity_at:string }
export interface SupportMessage { id:string; body:string; visibility:string; author_type:string; sequence:number|null; event:string; created_at:string; redacted:boolean; attachments:{id:string;mime:string;size:number}[] }
export interface HelpCategory {code:string;name:string;sort:number;active:boolean}
export interface HelpDraft {title:string;summary:string;body:string;keywords:string;pinned:boolean;sort:number;language:string;min_version:string;max_version:string}
export interface HelpArticle extends HelpDraft {id:string;category:string;revision:number;live:boolean;draft:HelpDraft;published:Partial<HelpDraft>}
export interface SupportConfig {accepting:boolean;pause_message:string;service_hours:string;contact:string;types:{code:string;name:string}[];revision:number;templates:string[];retention_days:number}
const base='/api/admin/v1/support/';
export const support={
 get:<T>(path:string,params?:Record<string,unknown>)=>http.get(base+path,{params}) as unknown as Promise<T>,
 post:<T>(path:string,data:unknown)=>http.post(base+path,data) as unknown as Promise<T>,
 patch:<T>(path:string,data:unknown)=>http.patch(base+path,data) as unknown as Promise<T>,
};
export const stateNames:Record<string,string>={submitted:'已提交',processing:'处理中',waiting_user:'待补充',resolved:'已答复',closed:'已结束'};

// Retain the original revision and key across response loss, including a tab reload.
export async function sendSupportMutation<T>(actor:number,id:string,endpoint:string,revision:number,payload:Record<string,unknown>):Promise<T>{
 const slot=`support-pending-${actor}-${id}-${endpoint}`;
 const signature=JSON.stringify(payload);
 let data:Record<string,unknown>|undefined;
 try{const saved=JSON.parse(sessionStorage.getItem(slot)??'null');if(saved?.signature===signature)data=saved.data;}catch{/* invalid saved draft */}
 if(!data){data={...payload,revision,client_request_id:crypto.randomUUID()};sessionStorage.setItem(slot,JSON.stringify({signature,data}));}
 try{const result=await support.post<T>(`tickets/${id}/${endpoint}/`,data);sessionStorage.removeItem(slot);return result;}
 catch(error){const status=(error as {status?:number}).status;if(status&&[400,403,404,409].includes(status))sessionStorage.removeItem(slot);throw error;}
}
