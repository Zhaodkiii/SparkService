<template>
  <div class="login-wrap">
    <a-card title="SparkService 管理后台登录" :bordered="false" class="login-card">
      <a-form layout="vertical" :model="form" @finish="onSubmit">
        <a-form-item label="用户名" name="username" :rules="[{ required: true, message: '请输入用户名' }]">
          <a-input v-model:value="form.username" />
        </a-form-item>
        <a-form-item label="密码" name="password" :rules="[{ required: true, message: '请输入密码' }]">
          <a-input-password v-model:value="form.password" />
        </a-form-item>
        <a-button type="primary" html-type="submit" :loading="loading" block>登录</a-button>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import { useAuthStore } from '../stores/auth';

const router = useRouter();
const auth = useAuthStore();
const loading = ref(false);

const form = reactive({
  username: '',
  password: '',
});

async function onSubmit() {
  try {
    loading.value = true;
    await auth.login(form.username, form.password);
    message.success('登录成功');
    router.replace('/dashboard');
  } catch (error: any) {
    message.error(error?.message || '登录失败');
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(120deg, #f0f5ff, #f6ffed);
}
.login-card {
  width: 420px;
}
</style>
