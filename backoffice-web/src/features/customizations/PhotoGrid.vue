<template>
  <div>
    <a-space wrap class="gallery-tools">
      <span>共 {{ photos.length }} 张，当前 {{ page }} / {{ pages }} 组</span>
      <a-button size="small" :disabled="page === 1" @click="change(-1)"
        >上一组</a-button
      >
      <a-button size="small" :disabled="page === pages" @click="change(1)"
        >下一组</a-button
      >
      <a-button size="small" :loading="loading" @click="loadImages"
        >加载 / 更新本组预览</a-button
      >
    </a-space>
    <p class="hint">照片按需从 OSS 加载；查看预览或下载不会经过业务服务器。</p>
    <a-alert
      v-if="error"
      :message="error"
      type="warning"
      show-icon
      style="margin-bottom: 12px"
    />
    <div class="photo-grid">
      <article
        v-for="p in visible"
        :key="p.id"
        class="photo-card"
        :class="{ selected: modelValue?.includes(p.id) }"
      >
        <div class="photo-frame">
          <img
            v-if="urls[p.id]?.thumbnail_url && !failed[p.id]"
            :src="urls[p.id]!.thumbnail_url!"
            :alt="`照片 ${p.position + 1}`"
            loading="lazy"
            @error="failed[p.id] = true"
            @click="preview = urls[p.id]?.url || undefined"
          />
          <button v-else class="photo-placeholder" @click="loadImages">
            {{
              p.available === false
                ? "照片已不可下载"
                : failed[p.id]
                  ? "加载失败，点击更新链接"
                  : "点击加载预览"
            }}
          </button>
        </div>
        <div class="photo-body">
          <strong>照片 {{ p.position + 1 }}</strong>
          <a-checkbox
            v-if="selectable"
            :checked="modelValue?.includes(p.id)"
            :disabled="disabled"
            @change="toggle(p.id)"
            >本候选实际使用</a-checkbox
          >
          <p>{{ p.note || "未填写备注" }}</p>
          <a-space size="small" wrap
            ><a-tag v-if="p.must_use" color="orange">必用</a-tag
            ><a-tag v-if="p.crop_allowed === false">不可裁切</a-tag
            ><a-tag v-if="p.cover_preferred" color="blue">封面偏好</a-tag
            ><a-tag v-if="p.removed">后续已移除，历史版本保留</a-tag></a-space
          >
          <small
            >{{
              p.width && p.height ? `${p.width} × ${p.height}` : "尺寸未登记"
            }}
            ·
            {{
              p.size ? (p.size / 1024 / 1024).toFixed(2) + " MiB" : "大小未登记"
            }}</small
          >
          <a
            v-if="urls[p.id]?.url"
            :href="urls[p.id]!.url!"
            target="_blank"
            rel="noreferrer"
            >下载该照片</a
          >
          <small v-if="p.available === false" class="warning"
            >资料已过期或不可用，请核对制作依据</small
          >
        </div>
      </article>
    </div>
    <a-modal
      :open="!!preview"
      title="制作照片预览"
      :footer="null"
      :width="900"
      @cancel="preview = undefined"
      ><img
        :src="preview"
        alt="制作照片大图"
        style="max-width: 100%; max-height: 75vh; display: block; margin: auto"
    /></a-modal>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from "vue";
import type { Photo } from "./types";
import { post } from "./useCustomizationWorkspace";
const props = defineProps<{
  requestID: string;
  submissionID?: number;
  photos: Photo[];
  selectable?: boolean;
  modelValue?: string[];
  disabled?: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string[]] }>();
const page = ref(1),
  loading = ref(false),
  error = ref(""),
  urls = ref<Record<string, Photo>>({}),
  failed = ref<Record<string, boolean>>({}),
  preview = ref<string>();
const pages = computed(() => Math.max(1, Math.ceil(props.photos.length / 6))),
  visible = computed(() =>
    props.photos.slice((page.value - 1) * 6, page.value * 6),
  );
let alive = true;
function change(delta: number) {
  page.value += delta;
  error.value = "";
}
function toggle(id: string) {
  const values = props.modelValue ?? [];
  emit(
    "update:modelValue",
    values.includes(id) ? values.filter((v) => v !== id) : [...values, id],
  );
}
async function loadImages() {
  if (loading.value) return;
  const items = visible.value.filter((p) => p.available !== false);
  if (!items.length) return;
  loading.value = true;
  error.value = "";
  try {
    const result = await post<{ assets: Photo[] }>(
      `requests/${props.requestID}/asset-urls/`,
      {
        asset_ids: items.map((p) => p.id),
        ...(props.submissionID ? { submission_id: props.submissionID } : {}),
      },
    );
    if (!alive) return;
    for (const p of result.assets) {
      urls.value[p.id] = p;
      delete failed.value[p.id];
    }
  } catch (e) {
    if (alive)
      error.value = e instanceof Error ? e.message : "照片预览获取失败，请重试";
  } finally {
    if (alive) loading.value = false;
  }
}
onBeforeUnmount(() => {
  alive = false;
});
</script>
<style scoped>
.gallery-tools {
  margin-top: 8px;
}
.hint {
  color: #7a8393;
  font-size: 12px;
}
.photo-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.photo-card {
  border: 1px solid #e6eaf0;
  border-radius: 10px;
  overflow: hidden;
}
.photo-card.selected {
  border-color: #1677ff;
  background: #f4f8ff;
}
.photo-frame {
  height: 172px;
  background: #f4f6f9;
  display: flex;
  align-items: center;
  justify-content: center;
}
.photo-frame img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  cursor: zoom-in;
}
.photo-placeholder {
  border: 0;
  background: none;
  color: #667085;
  padding: 20px;
  cursor: pointer;
}
.photo-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.photo-body p {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.photo-body small {
  color: #7a8393;
}
.photo-body .warning {
  color: #b7791f;
}
@media (max-width: 800px) {
  .photo-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 500px) {
  .photo-grid {
    grid-template-columns: 1fr;
  }
}
</style>
