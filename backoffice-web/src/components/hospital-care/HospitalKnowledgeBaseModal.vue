<template>
  <a-modal
    :open="open"
    :title="profile ? '编辑知识库' : '新建知识库'"
    :confirm-loading="saving"
    destroy-on-close
    @ok="submit"
    @cancel="$emit('update:open', false)"
  >
    <a-form layout="vertical">
      <a-form-item label="名称" required>
        <a-input v-model:value="form.name" />
      </a-form-item>
      <a-form-item label="关联科室">
        <a-select
          v-model:value="form.department_ids"
          mode="multiple"
          allow-clear
          show-search
          option-filter-prop="label"
          placeholder="仅用于筛选，不控制访问"
          :options="departmentOptions"
        />
      </a-form-item>
      <a-form-item label="简介">
        <a-textarea v-model:value="form.description" :rows="3" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { message } from 'ant-design-vue';
import {
  createKnowledgeBase,
  hospitalCareMessage,
  updateKnowledgeBase,
  type DepartmentRow,
  type KnowledgeBaseRow,
} from '../../api/modules/hospitalCare';

const props = defineProps<{
  open: boolean;
  hospitalId: string;
  departments: DepartmentRow[];
  profile?: KnowledgeBaseRow | null;
}>();

const emit = defineEmits<{
  'update:open': [value: boolean];
  saved: [];
}>();

const saving = ref(false);
const form = reactive({
  name: '',
  description: '',
  department_ids: [] as string[],
});
const departmentOptions = computed(() => props.departments.map((item) => ({ value: item.id, label: item.name })));

watch(
  () => [props.open, props.profile],
  () => {
    if (!props.open) {
      return;
    }
    form.name = props.profile?.name || '';
    form.description = props.profile?.description || '';
    form.department_ids = [...(props.profile?.department_ids || [])];
  },
);

async function submit() {
  if (!form.name.trim()) {
    message.error('请填写知识库名称');
    return;
  }
  saving.value = true;
  try {
    if (props.profile) {
      await updateKnowledgeBase(props.profile.id, {
        version: props.profile.version,
        name: form.name.trim(),
        description: form.description,
        department_ids: form.department_ids,
      });
      message.success('已保存知识库');
    } else {
      await createKnowledgeBase(props.hospitalId, {
        name: form.name.trim(),
        description: form.description,
        department_ids: form.department_ids,
      });
      message.success('已创建知识库');
    }
    emit('update:open', false);
    emit('saved');
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    saving.value = false;
  }
}
</script>
