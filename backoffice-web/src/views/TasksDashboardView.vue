<template>
  <a-row :gutter="16">
    <a-col :span="6"><a-card title="近24h任务总数">{{ data?.summary.total_recent ?? '-' }}</a-card></a-col>
    <a-col :span="6"><a-card title="周期任务总数">{{ data?.summary.periodic_total ?? '-' }}</a-card></a-col>
    <a-col :span="6"><a-card title="启用周期任务">{{ data?.summary.periodic_enabled ?? '-' }}</a-card></a-col>
    <a-col :span="6"><a-card title="失败任务">{{ data?.summary.status_counter.failure ?? '-' }}</a-card></a-col>
  </a-row>

  <a-card title="最近任务" style="margin-top: 16px">
    <a-table :data-source="data?.recent_tasks || []" :pagination="false" row-key="task_id">
      <a-table-column title="任务ID" data-index="task_id" />
      <a-table-column title="任务名" data-index="task_name" />
      <a-table-column title="状态" data-index="status" />
      <a-table-column title="完成时间" data-index="date_done" />
      <a-table-column title="结果" key="result">
        <template #default="{ record }">
          <span>{{ String(record.result || '').slice(0, 80) }}</span>
        </template>
      </a-table-column>
    </a-table>
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchTaskDashboard, type TaskSummaryResponse } from '../api/modules/tasks';

const data = ref<TaskSummaryResponse | null>(null);

onMounted(async () => {
  data.value = await fetchTaskDashboard();
});
</script>
