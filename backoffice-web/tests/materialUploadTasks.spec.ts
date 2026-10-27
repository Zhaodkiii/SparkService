import {beforeEach,describe,it,expect} from 'vitest';
import {readUploads,rememberUpload,forgetUpload,createUploadLimiter} from '../src/views/materialUploadTasks';

beforeEach(()=>localStorage.clear());
describe('recoverable direct OSS uploads',()=>{
  it('isolates accounts and stores no file bytes or credentials',()=>{
    const task={uploadID:'upload',libraryID:'pack',name:'flower.png',purpose:'sticker',createdAt:Date.now(),
      file:'private bytes',credentials:{secret:'secret'},url:'signed-url'};
    rememberUpload('account-a',task);
    expect(readUploads('account-b')).toEqual([]);
    expect(JSON.stringify(readUploads('account-a'))).not.toMatch(/secret|signed-url|private bytes/);
    forgetUpload('account-a','upload');expect(readUploads('account-a')).toEqual([]);
  });
  it('limits concurrent work and releases capacity after failures',async()=>{
    const limit=createUploadLimiter(3);let active=0,max=0;
    const results=await Promise.allSettled(Array.from({length:10},(_,index)=>limit(async()=>{
      active++;max=Math.max(max,active);await new Promise(resolve=>setTimeout(resolve,1));active--;
      if(index===1)throw new Error('upload failed');return index;
    })));
    expect(max).toBe(3);expect(results.filter(r=>r.status==='fulfilled')).toHaveLength(9);
  });
});
