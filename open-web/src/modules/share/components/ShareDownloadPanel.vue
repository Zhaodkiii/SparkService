<script setup lang="ts">
defineProps<{
  title: string;
  description: string;
  buttonText: string;
}>();

const emit = defineEmits<{
  download: [];
}>();
</script>

<template>
  <footer class="download-panel">
    <div>
      <h3>{{ title }}</h3>
      <p>{{ description }}</p>
    </div>
    <button class="primary-button" type="button" @click="emit('download')">
      {{ buttonText }}
    </button>
  </footer>
</template>
