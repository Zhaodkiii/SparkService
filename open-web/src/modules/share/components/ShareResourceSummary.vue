<script setup lang="ts">
import { computed } from 'vue';
import type { SharePublicPayload } from '../types';
import {
  asCasePayload,
  formatDate,
  formatDay,
  getResourceAttachments,
  getResourceStatusBadge,
  getResourceSummaryLines,
  getResourceTitle,
  resourceKindLabel,
} from '../utils';
import ShareAttachmentList from './ShareAttachmentList.vue';

const props = defineProps<{
  payload: SharePublicPayload;
}>();

const casePayload = computed(() => asCasePayload(props.payload));
const shareKind = computed(() => props.payload.share.business_type);
const resourceTitle = computed(() => getResourceTitle(props.payload));
const resourceStatusBadge = computed(() => getResourceStatusBadge(props.payload));
const resourceSummaryLines = computed(() => getResourceSummaryLines(props.payload));
const resourceAttachments = computed(() => getResourceAttachments(props.payload));
const shareExpires = computed(() => props.payload.share.expires_at);
</script>

<template>
  <section class="case-card">
    <div class="case-body">
      <template v-if="casePayload">
        <div class="case-head">
          <div>
            <p class="eyebrow">病例摘要</p>
            <h2>{{ casePayload.case.title }}</h2>
          </div>
          <span class="status-chip">{{ casePayload.case.status_badge_text || '病例' }}</span>
        </div>

        <div class="case-meta">
          <span>成员：{{ casePayload.member.display_name }}</span>
          <span v-if="casePayload.member.gender">性别：{{ casePayload.member.gender }}</span>
          <span v-if="casePayload.member.age_text">{{ casePayload.member.age_text }}</span>
        </div>

        <div class="case-summary">
          <p v-if="casePayload.case.diagnosis_summary">{{ casePayload.case.diagnosis_summary }}</p>
          <div class="summary-line">
            <span v-if="casePayload.case.hospital_name">{{ casePayload.case.hospital_name }}</span>
            <span v-if="casePayload.case.record_type">{{ casePayload.case.record_type }}</span>
            <span v-if="casePayload.case.created_at">{{ formatDay(casePayload.case.created_at) }}</span>
          </div>
        </div>

        <ShareAttachmentList :attachments="casePayload.case.attachments ?? []" />

        <div class="expires-note">
          <span>分享码</span>
          <strong>{{ casePayload.share.share_code }}</strong>
          <span>有效至 {{ formatDate(shareExpires) }}</span>
        </div>
      </template>

      <template v-else>
        <div class="case-head">
          <div>
            <p class="eyebrow">{{ resourceKindLabel(shareKind) }}摘要</p>
            <h2>{{ resourceTitle }}</h2>
          </div>
          <span class="status-chip">{{ resourceStatusBadge || resourceKindLabel(shareKind) }}</span>
        </div>

        <div class="case-meta">
          <span v-for="item in resourceSummaryLines" :key="item">{{ item }}</span>
        </div>

        <div class="case-summary">
          <p>{{ payload.share.title }}</p>
          <div class="summary-line">
            <span>类型：{{ resourceKindLabel(shareKind) }}</span>
            <span v-if="payload.share.business_id">编号：{{ payload.share.business_id }}</span>
            <span v-if="shareExpires">有效至 {{ formatDate(shareExpires) }}</span>
          </div>
        </div>

        <ShareAttachmentList :attachments="resourceAttachments" />

        <div class="expires-note">
          <span>分享码</span>
          <strong>{{ payload.share.share_code }}</strong>
          <span>有效至 {{ formatDate(shareExpires) }}</span>
        </div>
      </template>
    </div>
  </section>
</template>
