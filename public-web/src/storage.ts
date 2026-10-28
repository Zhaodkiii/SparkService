export function database():Promise<IDBDatabase>{return new Promise((resolve,reject)=>{const r=indexedDB.open('traveldiary-web',1);r.onupgradeneeded=()=>r.result.createObjectStore('drafts',{keyPath:'id'});r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)})}
export async function transact(mode:IDBTransactionMode,action:(s:IDBObjectStore)=>IDBRequest){const db=await database();return new Promise<any>((resolve,reject)=>{const tx=db.transaction('drafts',mode);const r=action(tx.objectStore('drafts'));tx.oncomplete=()=>{db.close();resolve(r.result)};tx.onerror=()=>{db.close();reject(tx.error)};tx.onabort=()=>{db.close();reject(tx.error)}})}
export const saveDraft=(d:any)=>transact('readwrite',s=>s.put(d))
export const listDrafts=()=>transact('readonly',s=>s.getAll())
export const deleteDraft=(id:string)=>transact('readwrite',s=>s.delete(id))
