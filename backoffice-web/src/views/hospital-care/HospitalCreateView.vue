<template>
  <a-spin :spinning="saving">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <a-space>
        <a-button @click="goBack">返回医院列表</a-button>
        <a-typography-title :level="4" style="margin: 0">新增医院</a-typography-title>
      </a-space>
    </div>
    <a-card :bordered="false">
      <HospitalBaseInfoForm :form="form" mode="create" />
      <div style="text-align: right">
        <a-space>
          <a-button @click="goBack">取消</a-button>
          <a-button type="primary" :loading="saving" @click="submit">保存草稿</a-button>
        </a-space>
      </div>
    </a-card>
  </a-spin>
</template>

<script setup lang="ts">
import { onBeforeUnmount, reactive, ref } from 'vue';
import { onBeforeRouteLeave, useRouter } from 'vue-router';
import { Modal, message } from 'ant-design-vue';
import { createHospital, hospitalCareMessage, type HospitalDraft } from '../../api/modules/hospitalCare';
import HospitalBaseInfoForm from '../../components/hospital-care/HospitalBaseInfoForm.vue';

const router = useRouter();
const saving = ref(false);
const dirty = ref(false);
const form = reactive<HospitalDraft>({
  code: '',
  name: '',
  short_name: '',
  grade: '',
  province_code: '',
  city_code: '',
  district_code: '',
  address: '',
  service_phone: '',
  emergency_phone: '',
  website_url: '',
  introduction: '',
  registration_redirect_url: '',
  service_mode: 'demo',
});

const stopWatch = watchForm();

function watchForm() {
  const initial = JSON.stringify(form);
  const timer = window.setInterval(() => {
    dirty.value = JSON.stringify(form) !== initial;
  }, 400);
  return () => window.clearInterval(timer);
}

function validate() {
  if (!form.name.trim() || !form.code.trim() || !form.province_code.trim() || !form.city_code.trim() || !form.address.trim()) {
    throw new Error('请填写官方名称、唯一编码、行政区划和详细地址');
  }
  if (form.service_mode === 'redirect' && !form.registration_redirect_url.trim()) {
    throw new Error('跳转模式必须填写官方入口地址');
  }
}

function confirmLeave(): Promise<boolean> {
  if (!dirty.value || saving.value) {
    return Promise.resolve(true);
  }
  return new Promise((resolve) => {
    Modal.confirm({
      title: '放弃未保存内容？',
      content: '当前表单尚未保存，离开后草稿不会保留。',
      okText: '离开',
      cancelText: '继续编辑',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    });
  });
}

async function goBack() {
  if (await confirmLeave()) {
    dirty.value = false;
    router.push('/hospital-care/hospitals');
  }
}

async function submit() {
  saving.value = true;
  try {
    validate();
    const created = await createHospital({ ...form });
    dirty.value = false;
    message.success('已保存为草稿医院');
    router.replace(`/hospital-care/hospitals/${created.id}`);
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    saving.value = false;
  }
}

onBeforeRouteLeave(async () => confirmLeave());
onBeforeUnmount(stopWatch);
</script>
