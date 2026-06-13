<template>
  <a-modal
    v-model:open="visible"
    :title="`用户 ${userId}`"
    width="92vw"
    :style="{ maxWidth: '1280px', top: '24px' }"
    :footer="null"
    destroy-on-close
  >
    <MedicalDataUserOverviewPanel v-if="visible" :user-id="userId" :active="visible" embedded />
  </a-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import MedicalDataUserOverviewPanel from './MedicalDataUserOverviewPanel.vue';

const props = defineProps<{
  open: boolean;
  userId: number;
}>();

const emit = defineEmits<{ 'update:open': [value: boolean] }>();

const visible = computed({
  get: () => props.open,
  set: (value: boolean) => emit('update:open', value),
});
</script>
