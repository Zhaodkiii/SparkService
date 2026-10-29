<script setup lang="ts">
import UnitThumb from './UnitThumb.vue'
import {base} from './book-api'
defineProps<{book:any}>()
</script>
<template><div class="template-preview-composition"><div class="template-cover"><img :src="book.cover" :alt="`${book.title}封面`" loading="lazy"></div><div class="template-spreads"><UnitThumb v-for="u in book.previewUnits" :key="book.id+u.id" :unit="u" :base="base(book)"/><div v-for="n in Math.max(0,2-(book.previewUnits?.length||0))" :key="n" class="spread-unavailable">暂无跨页预览</div></div></div></template>
