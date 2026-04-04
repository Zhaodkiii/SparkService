<template>
  <a-row :gutter="16">
    <a-col :span="10">
      <a-card title="角色列表">
        <a-space style="margin-bottom: 12px">
          <a-input v-model:value="roleForm.name" placeholder="角色名" />
          <a-input v-model:value="roleForm.code" placeholder="角色编码" />
          <a-button type="primary" @click="onCreateRole">新增角色</a-button>
        </a-space>
        <a-table :data-source="roles" row-key="id" :pagination="false" :row-selection="roleSelection">
          <a-table-column title="名称" data-index="name" />
          <a-table-column title="编码" data-index="code" />
          <a-table-column title="状态">
            <template #default="{ record }">{{ record.is_active ? '启用' : '禁用' }}</template>
          </a-table-column>
        </a-table>
      </a-card>
    </a-col>
    <a-col :span="14">
      <a-card title="权限列表">
        <a-table :data-source="permissions" row-key="code" :pagination="false" :row-selection="permSelection">
          <a-table-column title="名称" data-index="name" />
          <a-table-column title="编码" data-index="code" />
          <a-table-column title="类型" data-index="permission_type" />
          <a-table-column title="路径" data-index="path" />
        </a-table>
        <a-button type="primary" style="margin-top: 12px" @click="onAssignPermissions">保存角色权限</a-button>
      </a-card>
    </a-col>
  </a-row>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import { assignRolePermissions, createRole, fetchPermissions, fetchRolePermissions, fetchRoles, type PermissionItem, type RoleItem } from '../api/modules/rbac';

const roles = ref<RoleItem[]>([]);
const permissions = ref<PermissionItem[]>([]);
const selectedRoleId = ref<number | null>(null);
const selectedPermissionCodes = ref<string[]>([]);
const roleForm = reactive({ name: '', code: '', description: '' });

const roleSelection = computed(() => ({
  type: 'radio' as const,
  selectedRowKeys: selectedRoleId.value ? [selectedRoleId.value] : [],
  onChange: async (keys: (string | number)[]) => {
    selectedRoleId.value = Number(keys[0]);
    if (selectedRoleId.value) {
      const data = await fetchRolePermissions(selectedRoleId.value);
      selectedPermissionCodes.value = data.permission_codes;
    }
  },
}));

const permSelection = computed(() => ({
  selectedRowKeys: selectedPermissionCodes.value,
  onChange: (keys: (string | number)[]) => {
    selectedPermissionCodes.value = keys.map((k) => String(k));
  },
}));

async function load() {
  roles.value = await fetchRoles();
  permissions.value = await fetchPermissions();
}

async function onCreateRole() {
  if (!roleForm.name || !roleForm.code) {
    message.warning('请输入角色名与编码');
    return;
  }
  await createRole(roleForm);
  roleForm.name = '';
  roleForm.code = '';
  roleForm.description = '';
  message.success('角色已创建');
  await load();
}

async function onAssignPermissions() {
  if (!selectedRoleId.value) {
    message.warning('请先选择角色');
    return;
  }
  await assignRolePermissions(selectedRoleId.value, selectedPermissionCodes.value);
  message.success('角色权限已更新');
}

onMounted(load);
</script>
