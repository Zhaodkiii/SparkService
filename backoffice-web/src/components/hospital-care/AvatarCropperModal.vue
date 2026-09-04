<template>
  <a-modal :open="open" title="裁剪头像" :width="420" :mask-closable="false" @ok="confirm" @cancel="$emit('cancel')">
    <div class="cropper">
      <div
        ref="viewportRef"
        class="cropper__viewport"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
      >
        <img
          v-if="imageUrl"
          :src="imageUrl"
          class="cropper__image"
          :style="imageStyle"
          draggable="false"
          alt="待裁剪图片"
          @load="onImageLoad"
        />
        <div class="cropper__mask" />
      </div>
      <div class="cropper__zoom">
        <span>缩放</span>
        <a-slider v-model:value="zoom" :min="1" :max="3" :step="0.01" style="flex: 1" @change="clampOffset" />
      </div>
      <p class="cropper__tip">拖动图片调整位置，最终生成 1024×1024 正方形头像。</p>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';

const VIEWPORT = 320;

const props = defineProps<{
  open: boolean;
  imageUrl: string;
}>();

const emit = defineEmits<{
  confirm: [payload: { crop_x: number; crop_y: number; crop_size: number }];
  cancel: [];
}>();

const viewportRef = ref<HTMLElement | null>(null);
const zoom = ref(1);
const natural = reactive({ width: 0, height: 0 });
const offset = reactive({ x: 0, y: 0 });
const drag = reactive({ active: false, startX: 0, startY: 0, originX: 0, originY: 0 });

const baseScale = computed(() => {
  if (!natural.width || !natural.height) {
    return 1;
  }
  return VIEWPORT / Math.min(natural.width, natural.height);
});

const scale = computed(() => baseScale.value * zoom.value);

const displaySize = computed(() => ({
  width: natural.width * scale.value,
  height: natural.height * scale.value,
}));

const imageStyle = computed(() => ({
  width: `${displaySize.value.width}px`,
  height: `${displaySize.value.height}px`,
  transform: `translate(${offset.x}px, ${offset.y}px)`,
}));

function clampOffset() {
  const { width, height } = displaySize.value;
  offset.x = Math.min(0, Math.max(VIEWPORT - width, offset.x));
  offset.y = Math.min(0, Math.max(VIEWPORT - height, offset.y));
}

function onImageLoad(event: Event) {
  const img = event.target as HTMLImageElement;
  natural.width = img.naturalWidth;
  natural.height = img.naturalHeight;
  zoom.value = 1;
  // 默认居中
  offset.x = (VIEWPORT - displaySize.value.width) / 2;
  offset.y = (VIEWPORT - displaySize.value.height) / 2;
  clampOffset();
}

function onPointerDown(event: PointerEvent) {
  drag.active = true;
  drag.startX = event.clientX;
  drag.startY = event.clientY;
  drag.originX = offset.x;
  drag.originY = offset.y;
  viewportRef.value?.setPointerCapture(event.pointerId);
}

function onPointerMove(event: PointerEvent) {
  if (!drag.active) {
    return;
  }
  offset.x = drag.originX + (event.clientX - drag.startX);
  offset.y = drag.originY + (event.clientY - drag.startY);
  clampOffset();
}

function onPointerUp() {
  drag.active = false;
}

function round4(value: number) {
  return Math.round(value * 10000) / 10000;
}

function confirm() {
  if (!natural.width || !natural.height) {
    return;
  }
  const s = scale.value;
  const cropX = Math.min(1, Math.max(0, -offset.x / s / natural.width));
  const cropY = Math.min(1, Math.max(0, -offset.y / s / natural.height));
  let cropSize = VIEWPORT / s / Math.min(natural.width, natural.height);
  cropSize = Math.min(cropSize, 1 - cropX, 1 - cropY, 1);
  emit('confirm', { crop_x: round4(cropX), crop_y: round4(cropY), crop_size: round4(cropSize) });
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      zoom.value = 1;
      offset.x = 0;
      offset.y = 0;
    }
  },
);
</script>

<style scoped>
.cropper {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}
.cropper__viewport {
  position: relative;
  width: 320px;
  height: 320px;
  overflow: hidden;
  border-radius: 8px;
  background: #111;
  touch-action: none;
  cursor: grab;
}
.cropper__viewport:active {
  cursor: grabbing;
}
.cropper__image {
  position: absolute;
  top: 0;
  left: 0;
  user-select: none;
  max-width: none;
}
.cropper__mask {
  position: absolute;
  inset: 0;
  border: 2px solid rgba(255, 255, 255, 0.85);
  border-radius: 8px;
  pointer-events: none;
}
.cropper__zoom {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 320px;
}
.cropper__tip {
  margin: 0;
  color: #888;
  font-size: 12px;
}
</style>
