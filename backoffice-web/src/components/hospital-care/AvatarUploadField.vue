<template>
  <div class="avatar-upload-field">
    <AgentAvatar :src="previewUrl" :name="name" :size="72" />
    <div class="avatar-upload-field__actions">
      <a-button size="small" :loading="uploading" @click="triggerSelect">
        {{ previewUrl ? '重新上传' : '选择图片' }}
      </a-button>
      <span v-if="uploading" class="avatar-upload-field__hint">正在上传…</span>
      <div class="avatar-upload-field__hint">支持 JPG、PNG、WEBP，不超过 5 MB，最长边 2048 像素；保存后生效。</div>
      <a-alert v-if="error" type="error" show-icon :message="error" style="margin-top: 4px" />
    </div>
    <input
      ref="inputRef"
      type="file"
      accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
      style="display: none"
      @change="onFileChange"
    />
    <AvatarCropperModal :open="cropper.open" :image-url="cropper.imageUrl" @confirm="onCropConfirm" @cancel="closeCropper" />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import { hospitalCareMessage, uploadPublicImage, type AgentAvatarUploadResult } from '../../api/modules/hospitalCare';
import AgentAvatar from './AgentAvatar.vue';
import AvatarCropperModal from './AvatarCropperModal.vue';

/**
 * 通用头像上传字段：预览 + 前端预检 + 1:1 裁剪 + 公开上传接口。
 * 只负责拿到 file_id 与预览 URL，绑定到业务对象由调用方在保存时完成。
 */
const props = defineProps<{
  hospitalId: string;
  purpose: 'clinical_agent_avatar' | 'doctor_avatar';
  url?: string;
  name?: string;
}>();

const emit = defineEmits<{
  uploaded: [result: AgentAvatarUploadResult];
}>();

const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPT_EXT = ['jpg', 'jpeg', 'png', 'webp'];

const uploading = ref(false);
const error = ref('');
const uploadedUrl = ref('');
const inputRef = ref<HTMLInputElement | null>(null);
const cropper = reactive({ open: false, imageUrl: '', file: null as File | null });

const previewUrl = computed(() => uploadedUrl.value || props.url || '');

function triggerSelect() {
  error.value = '';
  inputRef.value?.click();
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) {
    return;
  }
  const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : '';
  if (!ACCEPT_EXT.includes(ext)) {
    error.value = '请选择 JPG、PNG 或 WEBP 图片';
    return;
  }
  if (file.size > MAX_BYTES) {
    error.value = '图片不能超过 5 MB';
    return;
  }
  closeCropper();
  cropper.file = file;
  cropper.imageUrl = URL.createObjectURL(file);
  cropper.open = true;
}

function closeCropper() {
  if (cropper.imageUrl) {
    URL.revokeObjectURL(cropper.imageUrl);
  }
  cropper.open = false;
  cropper.imageUrl = '';
  cropper.file = null;
}

async function onCropConfirm(params: { crop_x: number; crop_y: number; crop_size: number }) {
  const file = cropper.file;
  closeCropper();
  if (!file) {
    return;
  }
  const formData = new FormData();
  formData.append('file', file);
  formData.append('purpose', props.purpose);
  formData.append('hospital_id', props.hospitalId);
  formData.append('crop_x', String(params.crop_x));
  formData.append('crop_y', String(params.crop_y));
  formData.append('crop_size', String(params.crop_size));

  uploading.value = true;
  error.value = '';
  try {
    const result = await uploadPublicImage(formData);
    uploadedUrl.value = result.avatar_url;
    emit('uploaded', result);
    message.success('图片已上传，保存后生效');
  } catch (cause) {
    error.value = hospitalCareMessage(cause);
  } finally {
    uploading.value = false;
  }
}
</script>

<style scoped>
.avatar-upload-field {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.avatar-upload-field__actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}
.avatar-upload-field__hint {
  color: #888;
  font-size: 12px;
}
</style>
