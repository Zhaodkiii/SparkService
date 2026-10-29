/** Shared decoder pool: deduplicate requests and cap retained decoded pixels. */
export function createImagePool<T>(decode:(src:string)=>Promise<T>,cost:(value:T)=>number,budget=72*1024*1024,concurrency=3){
 const entries=new Map<string,{promise:Promise<T>,cost:number}>();let total=0,running=0;const queue:Array<()=>void>=[]
 function pump(){while(running<concurrency&&queue.length){running++;queue.shift()!()}}
 function get(src:string):Promise<T>{const existing=entries.get(src);if(existing){entries.delete(src);entries.set(src,existing);return existing.promise}
 let resolve!:(v:T)=>void,reject!:(e:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b}),entry={promise,cost:0};entries.set(src,entry)
 queue.push(()=>{decode(src).then(value=>{entry.cost=cost(value);total+=entry.cost;resolve(value);for(const [key,item]of entries){if(total<=budget)break;if(item.cost){total-=item.cost;entries.delete(key)}}},error=>{if(entries.get(src)===entry)entries.delete(src);reject(error)}).finally(()=>{running--;pump()})});pump();return promise}
 return {get}
}
