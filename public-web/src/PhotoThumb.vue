<script lang="ts">
const requests=new Map<string,{at:number,promise:Promise<any>}>()
</script>
<script setup lang="ts">
import {ref,onMounted} from 'vue'
import {api} from './book-api'
const props=defineProps<{base:string,pageId:string,layerId:string,label:string,replacement?:string}>()
const url=ref(''),failed=ref(false)
onMounted(async()=>{const path=props.base+`pages/${props.pageId}/slots/`;let cached=requests.get(path);if(!cached||Date.now()-cached.at>600000){cached={at:Date.now(),promise:api(path)};requests.set(path,cached)}try{const result=await cached.promise;url.value=result.items.find((s:any)=>s.layerId===props.layerId)?.url||''}catch{requests.delete(path);failed.value=true}})
</script>
<template><div class="photo-thumbnail"><img v-if="replacement||url" :src="replacement||url" :alt="label" @error="failed=true" v-show="!failed||!!replacement"><span v-if="(!replacement&&!url)||(failed&&!replacement)" class="thumb-placeholder">▧</span><b class="replace-badge" aria-hidden="true">↻</b></div></template>
