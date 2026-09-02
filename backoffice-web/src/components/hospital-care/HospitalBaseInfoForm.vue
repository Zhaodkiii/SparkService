<template>
  <a-form layout="vertical">
    <a-typography-title :level="5">基本信息</a-typography-title>
    <a-row :gutter="16">
      <a-col :xs="24" :md="12">
        <a-form-item label="医院官方名称" required>
          <a-input v-model:value="form.name" :disabled="disabled" placeholder="例如：天长市中医院" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item label="医院简称">
          <a-input v-model:value="form.short_name" :disabled="disabled" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item label="医院唯一编码" required>
          <a-input v-model:value="form.code" :disabled="disabled || mode === 'edit'" placeholder="创建后不可随意修改" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item label="医院等级">
          <a-select v-model:value="form.grade" :disabled="disabled" allow-clear show-search :options="GRADE_OPTIONS" placeholder="请选择" />
        </a-form-item>
      </a-col>
    </a-row>

    <a-typography-title :level="5">地址与联系方式</a-typography-title>
    <a-row :gutter="16">
      <a-col :xs="24" :md="8">
        <a-form-item label="省编码" required>
          <a-input v-model:value="form.province_code" :disabled="disabled" placeholder="例如 340000" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item label="市编码" required>
          <a-input v-model:value="form.city_code" :disabled="disabled" placeholder="例如 341100" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item label="区编码">
          <a-input v-model:value="form.district_code" :disabled="disabled" />
        </a-form-item>
      </a-col>
      <a-col :span="24">
        <a-form-item label="详细地址" required>
          <a-input v-model:value="form.address" :disabled="disabled" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item label="服务电话">
          <a-input v-model:value="form.service_phone" :disabled="disabled" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item label="急诊电话">
          <a-input v-model:value="form.emergency_phone" :disabled="disabled" />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-form-item label="官方网站">
          <a-input v-model:value="form.website_url" :disabled="disabled" placeholder="https://" />
        </a-form-item>
      </a-col>
    </a-row>

    <a-typography-title :level="5">服务模式</a-typography-title>
    <a-form-item required>
      <a-radio-group v-model:value="form.service_mode" :disabled="disabled">
        <a-radio value="demo">Demo 演示</a-radio>
        <a-radio value="redirect">跳转医院官方入口</a-radio>
        <a-radio value="integrated">已对接 HIS</a-radio>
      </a-radio-group>
    </a-form-item>
    <a-form-item v-if="form.service_mode === 'redirect'" label="跳转地址" required>
      <a-input v-model:value="form.registration_redirect_url" :disabled="disabled" placeholder="https://hospital.example/registration" />
    </a-form-item>
    <a-alert
      v-if="form.service_mode === 'integrated'"
      type="warning"
      show-icon
      message="HIS 接入尚未配置完成前只能保存草稿，不能启用。"
      style="margin-bottom: 16px"
    />
    <a-form-item label="医院简介">
      <a-textarea v-model:value="form.introduction" :disabled="disabled" :rows="4" />
    </a-form-item>
  </a-form>
</template>

<script setup lang="ts">
import type { HospitalDraft } from '../../api/modules/hospitalCare';
import { GRADE_OPTIONS } from '../../views/hospital-care/hospitalCareLabels';

defineProps<{
  form: HospitalDraft;
  mode: 'create' | 'edit';
  disabled?: boolean;
}>();
</script>
