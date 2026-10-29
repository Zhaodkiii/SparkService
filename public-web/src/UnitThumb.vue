<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue'
import {api} from './book-api'
const props=defineProps<{unit:any,base:string}>(),root=ref<HTMLElement>(),images=ref<string[]>([])
let observer:IntersectionObserver
onMounted(()=>{observer=new IntersectionObserver(async entries=>{if(!entries.some(e=>e.isIntersecting))return;observer.disconnect();for(const id of [props.unit.leftPageID,props.unit.rightPageID]){if(!id){images.value.push('');continue}try{images.value.push((await api(props.base+`pages/${id}/preview/?small=1`)).url)}catch{images.value.push('')}}},{rootMargin:'100px'});if(root.value)observer.observe(root.value)})
onBeforeUnmount(()=>observer?.disconnect())
</script>
<template><div ref="root" class="thumb-spread"><div v-for="(url,i) in images.length?images:['','']" :key="i"><img v-if="url" :src="url" alt="页面缩略图" loading="lazy"></div></div></template>
