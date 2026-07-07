<script setup lang="ts">
defineProps<{
  showFooter?: boolean;
}>();
</script>

<template>
  <div class="public-page">
    <slot name="banner" />
    <main class="public-page__main">
      <slot />
    </main>
    <footer v-if="showFooter !== false" class="public-page__footer">
      <slot name="footer">
        <p class="public-page__footer-text">© 小鲸健康</p>
      </slot>
    </footer>
  </div>
</template>

<style scoped>
.public-page__footer {
  padding: 24px 20px;
  text-align: center;
  border-top: 1px solid #f0f0f0;
  background: #fff;
}

.public-page__footer-text {
  margin: 0;
  font-size: 13px;
  color: #999;
}
</style>
