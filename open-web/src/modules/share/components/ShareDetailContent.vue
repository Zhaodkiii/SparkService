<script setup lang="ts">
import { computed } from 'vue';
import type { ShareCasePayload, ShareTimelineEvent } from '../types';
import type { NonCaseSharePayload } from '../utils';
import { formatDate, formatDay, isBusinessType, joinText, resourceKindLabel } from '../utils';
import ShareAttachmentList from './ShareAttachmentList.vue';

const props = defineProps<{
  mode: 'resource' | 'event';
  resourcePayload?: NonCaseSharePayload | null;
  event?: ShareTimelineEvent | null;
  casePayload?: ShareCasePayload | null;
}>();

const healthExam = computed(() =>
  props.resourcePayload && isBusinessType(props.resourcePayload, 'health_exam_report')
    ? props.resourcePayload
    : null,
);
const examination = computed(() =>
  props.resourcePayload && isBusinessType(props.resourcePayload, 'examination_report')
    ? props.resourcePayload
    : null,
);
const prescription = computed(() =>
  props.resourcePayload && isBusinessType(props.resourcePayload, 'prescription')
    ? props.resourcePayload
    : null,
);
const medicationPlan = computed(() =>
  props.resourcePayload && isBusinessType(props.resourcePayload, 'medication_plan')
    ? props.resourcePayload
    : null,
);
const medicineBox = computed(() =>
  props.resourcePayload && isBusinessType(props.resourcePayload, 'medicine_box')
    ? props.resourcePayload
    : null,
);
</script>

<template>
  <section v-if="mode === 'resource' && resourcePayload" class="timeline-section">
    <div class="section-head">
      <h3>详细信息</h3>
      <p>{{ resourceKindLabel(resourcePayload.share.business_type) }}</p>
    </div>

    <template v-if="healthExam">
      <div class="detail-grid">
        <div class="detail-field">
          <span>机构</span>
          <strong>{{ healthExam.report.institution_name || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>报告号</span>
          <strong>{{ healthExam.report.report_no || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>时间</span>
          <strong>{{ formatDay(healthExam.report.exam_date) || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>状态</span>
          <strong>{{ healthExam.report.status ?? '—' }}</strong>
        </div>
      </div>
      <div class="detail-block">
        <span>摘要</span>
        <p>{{ healthExam.report.summary || '—' }}</p>
      </div>
      <div v-if="healthExam.med_exam_details?.length" class="nested-detail-grid">
        <article
          v-for="detail in healthExam.med_exam_details"
          :key="detail.id"
          class="nested-plan nested-plan-detail"
        >
          <strong>{{ detail.item_name }}</strong>
          <span>{{ joinText([detail.category, detail.sub_category]) || '—' }}</span>
          <span>{{ joinText([detail.result_value, detail.unit]) || '—' }}</span>
          <span v-if="detail.reference_range">参考：{{ detail.reference_range }}</span>
        </article>
      </div>
    </template>

    <template v-else-if="examination">
      <div class="detail-grid">
        <div class="detail-field">
          <span>机构</span>
          <strong>{{ examination.report.organization_name || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>报告号</span>
          <strong>{{ examination.report.item_name || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>时间</span>
          <strong>{{
            formatDate(examination.report.reported_at || examination.report.performed_at) || '—'
          }}</strong>
        </div>
        <div class="detail-field">
          <span>状态</span>
          <strong>{{ examination.report.status ?? '—' }}</strong>
        </div>
      </div>
      <div class="detail-block">
        <span>摘要</span>
        <p>{{ examination.report.impression || examination.report.findings || '—' }}</p>
      </div>
      <div v-if="examination.med_exam_details?.length" class="nested-detail-grid">
        <article
          v-for="detail in examination.med_exam_details"
          :key="detail.id"
          class="nested-plan nested-plan-detail"
        >
          <strong>{{ detail.item_name }}</strong>
          <span>{{ joinText([detail.category, detail.sub_category]) || '—' }}</span>
          <span>{{ joinText([detail.result_value, detail.unit]) || '—' }}</span>
          <span v-if="detail.reference_range">参考：{{ detail.reference_range }}</span>
        </article>
      </div>
    </template>

    <template v-else-if="prescription">
      <div class="detail-grid">
        <div class="detail-field">
          <span>处方标题</span>
          <strong>{{ prescription.prescription.title }}</strong>
        </div>
        <div class="detail-field">
          <span>开方时间</span>
          <strong>{{ formatDate(prescription.prescription.prescribed_at) || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>处方状态</span>
          <strong>{{ prescription.prescription.status || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>诊断</span>
          <strong>{{ prescription.prescription.diagnosis || '—' }}</strong>
        </div>
      </div>
      <div v-if="prescription.medication_plans?.length" class="nested-detail-grid">
        <article
          v-for="plan in prescription.medication_plans"
          :key="plan.id"
          class="nested-plan nested-plan-detail"
        >
          <strong>{{ plan.drug_name || '未命名药品' }}</strong>
          <span>{{ joinText([plan.dose_per_time, plan.frequency_text]) || '暂无剂量与频次' }}</span>
          <span v-if="plan.box_name">药箱：{{ plan.box_name }}</span>
          <span v-if="plan.start_date">开始：{{ formatDay(plan.start_date) }}</span>
        </article>
      </div>
    </template>

    <template v-else-if="medicationPlan">
      <div class="detail-grid">
        <div class="detail-field">
          <span>药品名称</span>
          <strong>{{ medicationPlan.medication_plan.drug_name || '未命名药品' }}</strong>
        </div>
        <div class="detail-field">
          <span>单次剂量</span>
          <strong>{{ medicationPlan.medication_plan.dose_per_time || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>频次</span>
          <strong>{{ medicationPlan.medication_plan.frequency_text || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>开始日期</span>
          <strong>{{ formatDay(medicationPlan.medication_plan.start_date) || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>状态</span>
          <strong>{{ medicationPlan.medication_plan.status || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>药箱</span>
          <strong>{{ medicationPlan.linked_medicine_box?.medicine_name || '—' }}</strong>
        </div>
      </div>
      <div class="detail-block">
        <span>说明</span>
        <p>{{ medicationPlan.medication_plan.instructions || '—' }}</p>
      </div>
      <div
        v-if="medicationPlan.linked_prescription || medicationPlan.linked_medical_case"
        class="nested-detail-grid"
      >
        <article v-if="medicationPlan.linked_prescription" class="nested-plan nested-plan-detail">
          <strong>{{ medicationPlan.linked_prescription.title }}</strong>
          <span>{{ medicationPlan.linked_prescription.diagnosis || '—' }}</span>
          <span v-if="medicationPlan.linked_prescription.prescribed_at">
            开方：{{ formatDate(medicationPlan.linked_prescription.prescribed_at) }}
          </span>
        </article>
        <article v-if="medicationPlan.linked_medical_case" class="nested-plan nested-plan-detail">
          <strong>{{ medicationPlan.linked_medical_case.title || '病例' }}</strong>
          <span>{{ medicationPlan.linked_medical_case.hospital_name || '—' }}</span>
          <span v-if="medicationPlan.linked_medical_case.diagnosis_summary">
            {{ medicationPlan.linked_medical_case.diagnosis_summary }}
          </span>
        </article>
      </div>
      <div v-if="medicationPlan.medication_records.length" class="nested-detail-grid">
        <article
          v-for="record in medicationPlan.medication_records"
          :key="record.id"
          class="nested-plan nested-plan-detail"
        >
          <strong>{{ formatDate(record.scheduled_at) }}</strong>
          <span>{{ record.status || '—' }}</span>
          <span>{{ joinText([record.planned_dose, record.actual_dose]) || '—' }}</span>
        </article>
      </div>
    </template>

    <template v-else-if="medicineBox">
      <div class="detail-grid">
        <div class="detail-field">
          <span>药品名称</span>
          <strong>{{ medicineBox.medicine_box.medicine_name }}</strong>
        </div>
        <div class="detail-field">
          <span>品牌</span>
          <strong>{{ medicineBox.medicine_box.brand_name || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>剂型</span>
          <strong>{{ medicineBox.medicine_box.dosage_form || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>规格</span>
          <strong>{{ medicineBox.medicine_box.strength || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>库存</span>
          <strong>{{ medicineBox.medicine_box.total_quantity ?? '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>有效期</span>
          <strong>{{ formatDay(medicineBox.medicine_box.expire_date) || '—' }}</strong>
        </div>
      </div>
      <div class="detail-block">
        <span>备注</span>
        <p>{{ medicineBox.medicine_box.notes || '—' }}</p>
      </div>
      <div v-if="medicineBox.linked_medication_plans?.length" class="nested-detail-grid">
        <article
          v-for="plan in medicineBox.linked_medication_plans"
          :key="plan.id"
          class="nested-plan nested-plan-detail"
        >
          <strong>{{ plan.drug_name || '未命名药品' }}</strong>
          <span>{{ joinText([plan.dose_per_time, plan.frequency_text]) || '暂无剂量与频次' }}</span>
          <span v-if="plan.start_date">开始：{{ formatDay(plan.start_date) }}</span>
        </article>
      </div>
    </template>
  </section>

  <template v-else-if="mode === 'event' && event">
    <section class="detail-section">
      <p class="detail-lead">{{ event.detail || '暂无补充说明' }}</p>
    </section>

    <section v-if="event.kind === 'prescription' && event.prescription" class="detail-section">
      <div class="section-head"><h3>处方信息</h3></div>
      <div class="detail-grid">
        <div class="detail-field">
          <span>处方标题</span>
          <strong>{{ event.prescription.title }}</strong>
        </div>
        <div class="detail-field">
          <span>开方时间</span>
          <strong>{{ formatDate(event.prescription.prescribed_at) || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>处方状态</span>
          <strong>{{ event.prescription.status || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>处方说明</span>
          <strong>{{ event.prescription.diagnosis || '—' }}</strong>
        </div>
      </div>
    </section>

    <section
      v-if="event.kind === 'prescription' && event.nested_medication_plans?.length"
      class="detail-section"
    >
      <div class="section-head">
        <h3>服药计划</h3>
        <p>{{ event.nested_medication_plans.length }} 项</p>
      </div>
      <div class="nested-detail-grid">
        <article
          v-for="plan in event.nested_medication_plans"
          :key="plan.id"
          class="nested-plan nested-plan-detail"
        >
          <strong>{{ plan.drug_name || '未命名药品' }}</strong>
          <span>{{ joinText([plan.dose_per_time, plan.frequency_text]) || '暂无剂量与频次' }}</span>
          <span v-if="plan.box_name">药箱：{{ plan.box_name }}</span>
          <span v-if="plan.start_date">开始：{{ formatDay(plan.start_date) }}</span>
          <span v-if="plan.status">状态：{{ plan.status }}</span>
        </article>
      </div>
    </section>

    <section v-if="event.kind === 'medication' && event.medication_plan" class="detail-section">
      <div class="section-head"><h3>服药计划详情</h3></div>
      <div class="detail-grid">
        <div class="detail-field">
          <span>药品名称</span>
          <strong>{{ event.medication_plan.drug_name || '未命名药品' }}</strong>
        </div>
        <div class="detail-field">
          <span>单次剂量</span>
          <strong>{{ event.medication_plan.dose_per_time || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>频次</span>
          <strong>{{ event.medication_plan.frequency_text || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>开始日期</span>
          <strong>{{ formatDay(event.medication_plan.start_date) || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>状态</span>
          <strong>{{ event.medication_plan.status || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>药箱</span>
          <strong>{{ event.medication_plan.box_name || '—' }}</strong>
        </div>
      </div>
    </section>

    <section v-if="event.kind === 'examination' && event.examination" class="detail-section">
      <div class="section-head"><h3>检查详情</h3></div>
      <div class="detail-grid">
        <div class="detail-field">
          <span>检查分类</span>
          <strong>{{ event.examination.category || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>检查子类</span>
          <strong>{{ event.examination.sub_category || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>项目名称</span>
          <strong>{{ event.examination.item_name || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>检查时间</span>
          <strong>{{
            formatDate(event.examination.reported_at || event.examination.performed_at) || '—'
          }}</strong>
        </div>
        <div class="detail-field">
          <span>分类汇总</span>
          <strong>{{
            joinText([event.examination.category, event.examination.sub_category]) || '—'
          }}</strong>
        </div>
        <div class="detail-field">
          <span>状态</span>
          <strong>{{ event.examination.status ?? '—' }}</strong>
        </div>
      </div>
      <div class="detail-block">
        <span>结论</span>
        <p>{{ event.examination.impression || event.examination.findings || '—' }}</p>
      </div>
      <div class="detail-block">
        <span>详情</span>
        <p>{{ event.examination.findings || '—' }}</p>
      </div>
    </section>

    <section v-if="event.kind === 'symptom' && event.symptom" class="detail-section">
      <div class="section-head"><h3>症状详情</h3></div>
      <div class="detail-grid">
        <div class="detail-field">
          <span>症状名称</span>
          <strong>{{ event.symptom.name || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>严重程度</span>
          <strong>{{ event.symptom.severity || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>部位</span>
          <strong>{{ event.symptom.body_part || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>开始时间</span>
          <strong>{{ formatDate(event.symptom.started_at) || '—' }}</strong>
        </div>
      </div>
      <div class="detail-block">
        <span>备注</span>
        <p>{{ event.symptom.notes || '—' }}</p>
      </div>
    </section>

    <section v-if="event.kind === 'visit' && event.visit" class="detail-section">
      <div class="section-head"><h3>就诊详情</h3></div>
      <div class="detail-grid">
        <div class="detail-field">
          <span>就诊类型</span>
          <strong>{{ event.visit.visit_type || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>科室</span>
          <strong>{{ event.visit.department || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>医生</span>
          <strong>{{ event.visit.doctor_name || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>号源</span>
          <strong>{{ event.visit.visit_no || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>时间</span>
          <strong>{{ formatDate(event.visit.visited_at) || '—' }}</strong>
        </div>
      </div>
      <div class="detail-block">
        <span>备注</span>
        <p>{{ event.visit.notes || '—' }}</p>
      </div>
    </section>

    <section v-if="event.kind === 'surgery' && event.surgery" class="detail-section">
      <div class="section-head"><h3>手术详情</h3></div>
      <div class="detail-grid">
        <div class="detail-field">
          <span>手术名称</span>
          <strong>{{ event.surgery.procedure_name || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>部位</span>
          <strong>{{ event.surgery.site || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>主刀医生</span>
          <strong>{{ event.surgery.surgeon || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>时间</span>
          <strong>{{ formatDate(event.surgery.performed_at) || '—' }}</strong>
        </div>
      </div>
      <div class="detail-block">
        <span>备注</span>
        <p>{{ event.surgery.notes || '—' }}</p>
      </div>
    </section>

    <section v-if="event.kind === 'follow_up' && event.follow_up" class="detail-section">
      <div class="section-head"><h3>随访详情</h3></div>
      <div class="detail-grid">
        <div class="detail-field">
          <span>随访方式</span>
          <strong>{{ event.follow_up.method || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>状态</span>
          <strong>{{ event.follow_up.status || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>计划时间</span>
          <strong>{{ formatDate(event.follow_up.planned_at) || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>完成时间</span>
          <strong>{{ formatDate(event.follow_up.completed_at) || '—' }}</strong>
        </div>
      </div>
      <div class="detail-block">
        <span>结果</span>
        <p>{{ event.follow_up.outcome || '—' }}</p>
      </div>
      <div class="detail-block">
        <span>下一步</span>
        <p>{{ event.follow_up.next_action || '—' }}</p>
      </div>
    </section>

    <section v-if="event.kind === 'meta' && casePayload" class="detail-section">
      <div class="section-head"><h3>病例信息</h3></div>
      <div class="detail-grid">
        <div class="detail-field">
          <span>病例名称</span>
          <strong>{{ casePayload.case.title }}</strong>
        </div>
        <div class="detail-field">
          <span>类型</span>
          <strong>{{ casePayload.case.record_type || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>医院</span>
          <strong>{{ casePayload.case.hospital_name || '—' }}</strong>
        </div>
        <div class="detail-field">
          <span>更新时间</span>
          <strong>{{
            formatDate(casePayload.case.updated_at || casePayload.case.created_at) || '—'
          }}</strong>
        </div>
      </div>
    </section>

    <section v-if="event.attachments?.length" class="detail-section">
      <div class="section-head">
        <h3>附件</h3>
        <p>{{ event.attachments.length }} 个</p>
      </div>
      <ShareAttachmentList :attachments="event.attachments" inline />
    </section>
  </template>
</template>
