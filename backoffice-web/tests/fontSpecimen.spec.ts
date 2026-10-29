import {describe,it,expect} from 'vitest';
import {missingFontCharacters} from '../src/views/fontSpecimen';
describe('font specimen coverage',()=>{
 it('rejects corrupt sfnt rather than silently substituting',()=>{
  expect(()=>missingFontCharacters(new ArrayBuffer(5),'测试')).toThrow();
 });
 it('distinguishes mapped Unicode from missing characters',()=>{
  const data=new ArrayBuffer(68),v=new DataView(data);
  v.setUint32(0,0x00010000);v.setUint16(4,1);
  v.setUint32(12,0x636d6170);v.setUint32(20,28);v.setUint32(24,40);
  v.setUint16(30,1);v.setUint16(32,3);v.setUint16(34,10);v.setUint32(36,12);
  v.setUint16(40,12);v.setUint32(44,28);v.setUint32(52,1);
  v.setUint32(56,65);v.setUint32(60,65);v.setUint32(64,1);
  expect(missingFontCharacters(data,'A')).toEqual([]);
  expect(missingFontCharacters(data,'ABB\n')).toEqual(['B']);
 });
});
