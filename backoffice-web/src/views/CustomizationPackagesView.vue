<script setup lang="ts">
import CustomizationPackagesPanel from '../components/billing/CustomizationPackagesPanel.vue';
</script>
<template><section class="packages-page"><h1>数字定制套餐</h1><p>配置数字定制的服务范围与钻石价格，已发出的报价保留原版本。</p><router-link to="/diary-customizations">返回专属定制 →</router-link><CustomizationPackagesPanel/></section></template>
<style scoped>.packages-page{padding:24px;background:white}.packages-page p{color:#64748b}</style>
