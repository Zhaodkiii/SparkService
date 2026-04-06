<template>
  <a-table :data-source="rows" row-key="scenario" :pagination="false">
    <a-table-column title="场景" key="label">
      <template #default="{ record }">{{ record.label }}</template>
    </a-table-column>
    <a-table-column title="场景键" data-index="scenario" />
    <a-table-column title="模型数" data-index="models_count" />
    <a-table-column title="激活" data-index="active_bindings" />
    <a-table-column title="默认模型" key="default_model">
      <template #default="{ record }">{{ record.default_model || '—' }}</template>
    </a-table-column>
    <a-table-column title="操作" key="op">
      <template #default="{ record }">
        <a-button type="link" size="small" @click="goMaintain(record.scenario)">维护模型</a-button>
      </template>
    </a-table-column>
  </a-table>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { fetchAIScenarioSummaries, type AIScenarioSummary } from '../api/modules/ai';

const router = useRouter();
const rows = ref<AIScenarioSummary[]>([]);

function goMaintain(scenarioKey: string) {
  router.push({ name: 'AIScenarioModels', params: { scenarioKey } });
}

async function load() {
  rows.value = await fetchAIScenarioSummaries();
}

onMounted(load);
</script>
