<template>
  <div class="image-gallery">
    <a-image-preview-group>
      <div v-for="(item, index) in images" :key="`${index}-${item.url}`" class="image-item">
        <a-image
          v-if="item.url"
          :src="item.url"
          :alt="item.name || `image-${index + 1}`"
          :width="96"
          :height="96"
          class="thumb"
          :fallback="fallback"
        />
        <div v-else class="image-unavailable">
          <PictureOutlined />
          <span>附件不可访问</span>
        </div>
      </div>
    </a-image-preview-group>
    <div v-if="images.length === 0" class="image-unavailable">无图片</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { PictureOutlined } from '@ant-design/icons-vue';

const props = defineProps<{
  payload: Record<string, unknown>;
}>();

const fallback =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><rect width="100%" height="100%" fill="#f5f5f5"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#999" font-size="12">不可用</text></svg>');

function pickUrl(item: Record<string, unknown>): string {
  for (const key of ['url', 'remoteURL', 'remoteUrl', 'previewURL', 'previewUrl', 'thumbnailURL', 'thumbnailUrl']) {
    const value = item[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return '';
}

function pickName(item: Record<string, unknown>): string {
  for (const key of ['name', 'fileName', 'filename', 'title']) {
    const value = item[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return '';
}

const images = computed(() => {
  const raw = props.payload.attachments || props.payload.images || [];
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const record = item as Record<string, unknown>;
      return {
        url: pickUrl(record),
        name: pickName(record),
        raw: record,
      };
    });
});
</script>

<style scoped>
.image-gallery {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.image-item {
  width: 96px;
  height: 96px;
}
.thumb {
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}
.image-unavailable {
  width: 96px;
  height: 96px;
  border-radius: 8px;
  border: 1px dashed #d9d9d9;
  color: #999;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  gap: 4px;
}
</style>
