<template>
  <main class="customizations">
    <div class="page-heading">
      <div>
        <h1>专属定制</h1>
        <p>从用户资料到专属手帐，每一次交付都有明确的制作依据。</p>
      </div>
      <a-button :loading="w.listLoading.value" @click="w.load()"
        >刷新列表</a-button
      >
    </div>
    <a-alert
      v-if="w.listError.value"
      :message="w.listError.value"
      type="error"
      show-icon
      closable
      @close="w.listError.value = ''"
    />
    <div class="task-grid">
      <button
        v-for="item in buckets"
        :key="item.key"
        class="task-card"
        :class="{ active: w.task.value === item.key }"
        @click="selectTask(item.key)"
      >
        <span>{{ item.title }}</span
        ><strong>{{ w.summary.value[item.key] ?? 0 }}</strong>
      </button>
    </div>
    <a-form layout="inline" class="filters" @finish="w.load(true)">
      <a-form-item
        ><a-input-search
          v-model:value="w.q.value"
          placeholder="主题 / 单号 / 用户名 / 用户 ID"
          allow-clear
          style="width: 300px"
          @search="w.load(true)"
      /></a-form-item>
      <a-form-item
        ><a-select
          v-model:value="w.status.value"
          style="width: 165px"
          @change="w.load(true)"
          ><a-select-option value="">全部业务状态</a-select-option
          ><a-select-option
            v-for="(label, key) in statusLabels"
            :key="key"
            :value="key"
            >{{ label }}</a-select-option
          ></a-select
        ></a-form-item
      >
      <a-form-item
        ><a-select
          v-model:value="w.assigned.value"
          placeholder="全部负责人"
          allow-clear
          style="width: 160px"
          @change="w.load(true)"
          ><a-select-option
            v-for="o in w.operators.value"
            :key="o.id"
            :value="o.id"
            >{{ o.name }}</a-select-option
          ></a-select
        ></a-form-item
      >
      <a-button @click="clearFilters">重置筛选</a-button>
    </a-form>
    <a-table
      :columns="columns"
      :data-source="w.rows.value"
      :loading="w.listLoading.value"
      row-key="id"
      :pagination="false"
      :scroll="{ x: 1000 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'title'"
          ><a @click="w.open(record.id)">{{ record.title || "未命名草稿" }}</a
          ><small class="secondary block">{{ record.number }}</small></template
        >
        <template v-else-if="column.key === 'user'"
          ><span>{{ record.owner_name }}</span
          ><small class="secondary block"
            >用户 {{ record.owner_id }}</small
          ></template
        >
        <template v-else-if="column.key === 'status'"
          ><a-tag :color="statusColor(record.status)">{{
            statusLabels[record.status] || record.status
          }}</a-tag>
          <div class="flags">
            <a-tag
              v-if="
                record.pending_submission && record.status === 'in_production'
              "
              color="orange"
              >新资料待确认</a-tag
            ><a-tag v-if="record.cancellation_requested" color="red"
              >用户申请取消</a-tag
            >
          </div></template
        >
        <template v-else-if="column.key === 'assigned'">{{
          record.assigned_name || "未分配"
        }}</template>
        <template v-else-if="column.key === 'due'"
          ><span :class="{ overdue: record.overdue }">{{
            formatDate(record.due_at)
          }}</span
          ><a-tag v-if="record.overdue" color="red">已逾期</a-tag></template
        >
        <template v-else-if="column.key === 'updated'">{{
          formatDate(record.updated_at)
        }}</template>
        <template v-else-if="column.key === 'open'"
          ><a-button type="link" @click="w.open(record.id)"
            >进入工作台</a-button
          ></template
        >
      </template>
      <template #emptyText
        ><a-empty description="当前筛选下没有定制需求"
      /></template>
    </a-table>
    <div class="pagination">
      <a-button
        :disabled="w.page.value === 1"
        @click="
          w.page.value--;
          w.load();
        "
        >上一页</a-button
      ><span>第 {{ w.page.value }} 页</span
      ><a-button
        :disabled="!w.next.value"
        @click="
          w.page.value++;
          w.load();
        "
        >下一页</a-button
      >
    </div>
    <a-drawer
      :open="!!d || w.opening.value || !!w.error.value"
      :width="'min(1240px, 100vw)'"
      title="定制制作工作台"
      :mask-closable="false"
      @close="w.close()"
    >
      <a-spin v-if="w.opening.value" tip="正在读取需求…" class="opening" />
      <div v-if="w.error.value" class="feedback">
        <a-alert
          :message="w.error.value"
          type="error"
          show-icon
          closable
          @close="w.error.value = ''"
        /><a-space v-if="w.pending.value" style="margin-top: 8px"
          ><a-button :loading="w.actionBusy.value" @click="w.retryAction"
            >重试上次操作</a-button
          ><a-button @click="w.reconcile">核对最新状态</a-button></a-space
        >
      </div>
      <a-alert
        v-if="w.success.value"
        :message="w.success.value"
        type="success"
        show-icon
        closable
        class="feedback"
        @close="w.success.value = ''"
      />
      <template v-if="d">
        <div class="workspace-head">
          <div>
            <div class="eyebrow">
              {{ d.number }} · 用户 {{ d.owner_name }}（{{ d.owner_id }}）
            </div>
            <h2>{{ d.title || "未命名草稿" }}</h2>
            <a-space wrap
              ><a-tag :color="statusColor(d.status)">{{
                statusLabels[d.status]
              }}</a-tag
              ><span>负责人：{{ d.assigned_name || "未分配" }}</span
              ><span>资料修订 {{ d.revision }}</span></a-space
            >
          </div>
          <a-button :loading="w.actionBusy.value" @click="w.refresh"
            >刷新当前需求</a-button
          >
          <div class="next-step">
            <strong>下一步</strong><span>{{ d.next_step }}</span>
          </div>
          <a-space wrap
            ><a-button
              v-if="w.allowed('accept')"
              type="primary"
              :disabled="
                w.actionBusy.value || e.submission !== d.latest_submission_id
              "
              @click="w.act('accept', { submission_id: e.submission })"
              >{{
                d.status === "in_production"
                  ? "确认新资料并切换制作依据"
                  : d.status === "revision_requested"
                    ? "开始修订"
                    : "受理需求"
              }}</a-button
            ><a-button
              v-if="w.allowed('request-info')"
              :disabled="w.actionBusy.value"
              @click="w.showDialog('request-info', '请用户补充资料')"
              >要求补充资料</a-button
            ><a-tag v-if="d.overdue" color="red">预计日期已逾期</a-tag
            ><span v-if="w.dirty.value" class="secondary"
              >有未保存的编辑</span
            ></a-space
          >
        </div>
        <a-alert
          v-if="d.cancellation_requested"
          message="用户已申请取消，请先查看动态中的申请说明，再决定是否取消需求。"
          type="warning"
          show-icon
          class="feedback"
        />
        <a-alert
          v-if="w.conflict.value"
          message="服务端已有新操作。你的输入已保留，请对比最新内容；确认后再提交。"
          type="warning"
          show-icon
          class="feedback"
          ><template #description
            ><div>
              服务器日期：{{ formatDate(d.due_at) }}；服务器内部备注：{{
                d.internal_note || "无"
              }}
            </div>
            <a-button size="small" @click="adoptServer"
              >使用服务器的日期与备注</a-button
            ></template
          ></a-alert
        >
        <a-tabs v-model:active-key="e.section" class="workspace-tabs">
          <a-tab-pane key="materials" tab="1 · 资料与制作依据">
            <div class="section-head">
              <div>
                <h3>查看提交资料</h3>
                <p class="secondary">
                  历史提交仅供对照；制作和交付必须绑定明确的提交版本。
                </p>
              </div>
              <a-select
                v-if="d.submissions.length"
                v-model:value="e.submission"
                style="min-width: 300px"
                ><a-select-option
                  v-for="s in d.submissions"
                  :key="s.id"
                  :value="s.id"
                  >提交 #{{ s.number }} · {{ formatDate(s.created_at) }}
                  {{ s.id === d.accepted_submission_id ? "· 正在制作" : "" }}
                  {{
                    s.id === d.latest_submission_id ? "· 最新" : ""
                  }}</a-select-option
                ></a-select
              >
            </div>
            <a-alert
              v-if="d.pending_submission && d.status === 'in_production'"
              message="用户补充了新资料，尚未成为制作依据。确认新资料前，不能上传或交付旧依据的候选。"
              type="warning"
              show-icon
              class="feedback"
            />
            <div class="basis-strip">
              <span
                >当前查看：{{
                  viewedSubmission
                    ? "提交 #" + viewedSubmission.number
                    : "尚未提交的草稿"
                }}</span
              ><span
                >制作依据：{{
                  acceptedSubmission
                    ? "提交 #" + acceptedSubmission.number
                    : "尚未受理"
                }}</span
              >
            </div>
            <a-card :title="content.title || '未命名主题'" size="small"
              ><a-descriptions :column="1" bordered
                ><a-descriptions-item
                  v-for="(label, key) in briefLabels"
                  :key="key"
                  :label="label"
                  ><span class="preserve">{{
                    content.brief[key] || "未填写"
                  }}</span></a-descriptions-item
                ></a-descriptions
              ></a-card
            >
            <h3 class="spaced">制作照片</h3>
            <PhotoGrid
              :key="`${d.id}:${e.submission || 'draft'}`"
              :request-i-d="d.id"
              :submission-i-d="e.submission"
              :photos="photos"
            />
            <a-card title="下载资料并进入 PSD 制作" size="small" class="spaced"
              ><p>
                当前提交 #{{
                  viewedSubmission?.number || "—"
                }}。清单包含这个提交的文字、照片要求与短期下载链接。
              </p>
              <a-space wrap
                ><a-button :disabled="!e.submission" @click="w.exportBrief"
                  >导出本提交制作清单</a-button
                ><a-button
                  :disabled="!e.submission || downloadBusy"
                  :loading="downloadBusy"
                  @click="downloadPhotos"
                  >批量下载本提交照片</a-button
                ><a-button :disabled="!e.submission" @click="copyCommand"
                  >复制 PSD 工具下载命令</a-button
                ></a-space
              >
              <p class="secondary spaced">
                {{
                  downloadStatus ||
                  "设计工作站通过 fetch-brief 下载整套资料；所有照片直接从 OSS 获取。"
                }}
              </p>
              <pre>{{ toolCommand }}</pre>
            </a-card>
          </a-tab-pane>
          <a-tab-pane key="production" tab="2 · 制作进度">
            <a-row :gutter="24"
              ><a-col :xs="24" :lg="14"
                ><a-card title="日期与内部备注"
                  ><a-form layout="vertical"
                    ><a-form-item label="预计交付日期"
                      ><a-date-picker
                        show-time
                        :value="e.due ? dayjs(e.due) : null"
                        :disabled="!w.allowed('production')"
                        style="width: 100%"
                        placeholder="选择本地日期与时间"
                        @change="dateChanged"
                      /><small class="secondary"
                        >按浏览器时区展示，保存时自动携带时区。</small
                      ></a-form-item
                    ><a-form-item label="内部备注（仅管理员可见）"
                      ><a-textarea
                        v-model:value="e.internalNote"
                        :rows="6"
                        :maxlength="5000"
                        :disabled="!w.allowed('production')" /></a-form-item
                    ><a-button
                      type="primary"
                      :disabled="
                        !w.allowed('production') || !w.productionChanged.value
                      "
                      :loading="w.actionBusy.value"
                      @click="
                        w.act('production', {
                          due_at: e.due,
                          internal_note: e.internalNote,
                        })
                      "
                      >保存日期与备注</a-button
                    ></a-form
                  ></a-card
                ></a-col
              >
              <a-col :xs="24" :lg="10"
                ><a-card title="制作负责人"
                  ><p>当前：{{ d.assigned_name || "未分配" }}</p>
                  <a-select
                    v-model:value="e.assignedTo"
                    placeholder="选择有制作权限的管理员"
                    style="width: 100%"
                    :disabled="!w.allowed('assign')"
                    ><a-select-option
                      v-for="o in w.operators.value"
                      :key="o.id"
                      :value="o.id"
                      >{{ o.name }}</a-select-option
                    ></a-select
                  ><a-button
                    class="spaced"
                    :disabled="
                      !w.allowed('assign') ||
                      !e.assignedTo ||
                      e.assignedTo === d.assigned_to
                    "
                    :loading="w.actionBusy.value"
                    @click="w.act('assign', { assigned_to: e.assignedTo })"
                    >确认转交</a-button
                  ></a-card
                ><a-card title="处理需求" class="spaced"
                  ><p class="secondary">
                    每次操作独立填写说明；提交后会记录用户动态，必要时发送通知。
                  </p>
                  <a-space wrap
                    ><a-button
                      :disabled="!w.allowed('reject') || w.actionBusy.value"
                      @click="w.showDialog('reject', '暂无法制作：填写原因')"
                      >暂无法制作</a-button
                    ><a-button
                      danger
                      :disabled="!w.allowed('cancel') || w.actionBusy.value"
                      @click="w.showDialog('cancel', '取消需求：填写原因')"
                      >取消需求</a-button
                    ></a-space
                  >
                  <p v-if="!w.allowed('production')" class="secondary spaced">
                    需求已结束，制作操作已关闭。
                  </p></a-card
                ></a-col
              ></a-row
            >
          </a-tab-pane>
          <a-tab-pane key="deliveries" tab="3 · 成品与交付">
            <a-card title="上传私有成品候选"
              ><a-alert
                v-if="!w.allowed('upload')"
                message="请先确认最新制作依据。需求结束或等待补充时不能上传成品。"
                type="info"
                show-icon
              />
              <p>
                制作依据：{{
                  acceptedSubmission
                    ? "提交 #" + acceptedSubmission.number
                    : "未确认"
                }}
                · 仅接收 PSD 工具导出的私有 .source.zip
              </p>
              <input
                :key="d.id + ':' + d.accepted_submission_id"
                type="file"
                accept=".zip"
                :disabled="!w.allowed('upload') || w.transferBusy.value"
                @change="chooseFile"
              />
              <div v-if="w.archive.value" class="archive-summary">
                <strong>{{ w.archive.value.name }}</strong
                ><span
                  >{{
                    (w.archive.value.size / 1024 / 1024).toFixed(1)
                  }}
                  MiB</span
                ><template v-if="w.archiveInfo.value"
                  ><span
                    >源包 v{{ w.archiveInfo.value.packageVersion }} ·
                    {{ w.archiveInfo.value.pageCount }} 页 ·
                    {{ w.archiveInfo.value.title }}</span
                  ><a-tag color="green">已匹配当前需求</a-tag></template
                >
              </div>
              <a-progress
                v-if="w.transferBusy.value && !w.archiveInfo.value"
                :percent="Math.floor(w.hashProgress.value * 100)"
                size="small"
              />
              <a-progress
                v-if="w.uploadProgress.value > 0"
                :percent="Math.floor(w.uploadProgress.value * 100)"
                size="small"
              />
              <p aria-live="polite">{{ w.uploadStage.value }}</p>
              <a-space
                ><a-button
                  type="primary"
                  :disabled="
                    !w.allowed('upload') ||
                    !w.archiveInfo.value ||
                    w.transferBusy.value ||
                    w.actionBusy.value
                  "
                  @click="w.upload"
                  >直传成品包</a-button
                ><a-button v-if="w.transferBusy.value" @click="w.pauseUpload"
                  >暂停准备 / 上传</a-button
                ></a-space
              >
              <p class="secondary spaced">
                文件按块读取并在独立线程计算摘要。上传 100%
                表示文件传输结束；候选准备好后还需逐版本验收和正式交付。
              </p>
            </a-card>
            <a-table
              size="small"
              class="spaced"
              :columns="jobColumns"
              :data-source="d.jobs.filter((j) => j.kind === 'delivery')"
              row-key="id"
              :pagination="false"
              :scroll="{ x: 650 }"
              ><template #bodyCell="{ column, record }"
                ><template v-if="column.key === 'status'"
                  ><a-tag>{{
                    jobLabels[record.status] || record.status
                  }}</a-tag></template
                ><template v-else-if="column.key === 'created'">{{
                  formatDate(record.created_at)
                }}</template
                ><template v-else-if="column.key === 'action'"
                  ><a-button
                    v-if="record.status === 'failed'"
                    size="small"
                    :disabled="
                      !w.allowed('upload') ||
                      record.submission_id !== d.accepted_submission_id
                    "
                    :loading="w.actionBusy.value"
                    @click="w.retryJob(record)"
                    >重试处理</a-button
                  ><span
                    v-else-if="['queued', 'processing'].includes(record.status)"
                    class="secondary"
                    >自动更新中</span
                  ></template
                ></template
              ></a-table
            >
            <h3 class="spaced">待验收候选（{{ candidates.length }}）</h3>
            <a-empty
              v-if="!candidates.length"
              description="还没有待验收的成品候选"
            />
            <a-card
              v-for="c in candidates"
              :key="c.id"
              class="spaced"
              :title="`候选 #${c.candidate_number} · 源包对应服务端版本 ${c.version}`"
              ><p>
                {{ c.title }} · {{ c.page_count }} 页 · 照片槽位
                {{ c.photo_slots }} · 可编辑文字 {{ c.text_slots }} · 制作依据
                {{ submissionLabel(c.submission_id) }}
              </p>
              <a-alert
                v-if="!canReview(d, c)"
                type="warning"
                show-icon
                message="此候选依据已过期或当前阶段不能交付，请使用最新资料重新制作。"
              />
              <a-button
                class="spaced"
                @click="
                  previewCandidate =
                    previewCandidate === c.id ? undefined : c.id
                "
                >{{
                  previewCandidate === c.id
                    ? "收起页面预览"
                    : "展开此候选页面预览"
                }}</a-button
              >
              <div v-if="previewCandidate === c.id" class="page-previews">
                <img
                  v-for="p in c.pages"
                  :key="p.id"
                  :src="p.preview_url || undefined"
                  :alt="p.title"
                  loading="lazy"
                  @click="w.preview.value = p.preview_url || undefined"
                />
              </div>
              <template v-if="canReview(d, c)"
                ><h4 class="spaced">本候选实际使用的照片</h4>
                <PhotoGrid
                  :key="d.id + ':' + c.id"
                  :request-i-d="d.id"
                  :submission-i-d="c.submission_id"
                  :photos="candidatePhotos(c)"
                  selectable
                  v-model="reviewFor(e, c.id).used"
                  :disabled="w.actionBusy.value"
                />
                <a-checkbox
                  class="spaced"
                  v-model:checked="reviewFor(e, c.id).reviewed"
                  :disabled="w.actionBusy.value"
                  >已对这个候选完成 iOS
                  页面视觉、照片替换和文字编辑验收</a-checkbox
                ><a-textarea
                  class="spaced"
                  v-model:value="reviewFor(e, c.id).message"
                  placeholder="仅此候选的交付说明（用户可见）"
                  :rows="3"
                  :maxlength="3000"
                />
                <p class="secondary">
                  {{
                    reviewProblem(d, c, e) || "验收条件已满足，可以正式交付。"
                  }}
                </p>
                <a-popconfirm
                  :title="`确认将候选 #${c.candidate_number} 交付给 ${d.owner_name}（用户 ${d.owner_id}）？`"
                  @confirm="w.deliver(c.id)"
                  ><a-button
                    type="primary"
                    :disabled="!!reviewProblem(d, c, e) || w.actionBusy.value"
                    :loading="w.actionBusy.value"
                    >正式交付这个版本</a-button
                  ></a-popconfirm
                ></template
              >
            </a-card>
            <h3 class="spaced">当前与历史交付</h3>
            <a-empty
              v-if="!published.length"
              description="还没有正式交付"
            /><a-card
              v-for="c in published"
              :key="c.id"
              class="spaced"
              :title="`交付第 ${c.published_number || c.number} 版 · ${c.status === 'withdrawn' ? '已撤回' : d.current_delivery_id === c.id ? '当前交付' : '历史交付'}`"
              ><p>
                {{ c.title }} · {{ c.page_count }} 页 ·
                {{ submissionLabel(c.submission_id) }}
              </p>
              <p class="preserve">{{ c.note || "未填写交付说明" }}</p>
              <a-space
                ><a-button
                  @click="
                    previewCandidate =
                      previewCandidate === c.id ? undefined : c.id
                  "
                  >展开 / 收起预览</a-button
                ><a-button
                  v-if="
                    c.status === 'delivered' && d.current_delivery_id !== c.id
                  "
                  :disabled="!w.allowed('rollback') || w.actionBusy.value"
                  @click="
                    w.showDialog(
                      'rollback',
                      '将历史版本设为当前交付：填写原因',
                      c.id,
                    )
                  "
                  >设为当前交付</a-button
                ><a-button
                  v-if="c.status === 'delivered'"
                  danger
                  :disabled="!w.allowed('withdraw') || w.actionBusy.value"
                  @click="
                    w.showDialog('withdraw', '撤回这个交付版本：填写原因', c.id)
                  "
                  >撤回此版本</a-button
                ></a-space
              >
              <div v-if="previewCandidate === c.id" class="page-previews">
                <img
                  v-for="p in c.pages"
                  :key="p.id"
                  :src="p.preview_url || undefined"
                  :alt="p.title"
                  loading="lazy"
                  @click="w.preview.value = p.preview_url || undefined"
                /></div
            ></a-card>
          </a-tab-pane>
          <a-tab-pane key="activity" tab="4 · 通知与操作记录">
            <a-card title="通知投递"
              ><a-space
                ><a-button
                  :disabled="
                    !w.allowed('remind') ||
                    reminderCooling ||
                    w.actionBusy.value
                  "
                  :loading="w.actionBusy.value"
                  @click="w.act('remind')"
                  >发送待办提醒</a-button
                ><router-link to="/notifications/apns"
                  >完整 APNs 投递记录</router-link
                ></a-space
              >
              <p class="secondary spaced">
                {{
                  reminderCooling
                    ? "下次可提醒时间：" + formatDate(d.reminder_available_at)
                    : "每小时最多一次；只对待补充或待查看成品发送提醒。"
                }}
              </p>
              <p class="secondary">
                APNs 已受理不表示用户已看到，推送失败不影响领取成品。
              </p>
              <a-list :data-source="d.notifications"
                ><template #renderItem="{ item }"
                  ><a-list-item
                    ><div>
                      <strong>{{ noticeTitle(item.scene) }}</strong>
                      <p>{{ notificationText(item) }}</p>
                      <small class="secondary"
                        >{{ formatDate(item.created_at) }} · 通知记录
                        {{ item.id
                        }}<template v-if="item.deliveries.length">
                          · 已尝试
                          {{
                            item.deliveries.at(-1)?.attempt_count
                          }}
                          次</template
                        ></small
                      >
                      <div v-if="item.deliveries.at(-1)?.message_id">
                        <router-link
                          :to="{
                            path: '/notifications/apns',
                            query: {
                              message_id: item.deliveries.at(-1)?.message_id,
                            },
                          }"
                          >查看这条通知的完整投递记录</router-link
                        >
                      </div>
                    </div></a-list-item
                  ></template
                ><template #empty
                  ><a-empty description="暂无通知记录" /></template></a-list
            ></a-card>
            <a-row :gutter="24" class="spaced"
              ><a-col :xs="24" :lg="12"
                ><h3>用户可见动态</h3>
                <a-timeline
                  ><a-timeline-item
                    v-for="event in [...d.events].reverse()"
                    :key="event.id"
                    ><strong>{{
                      eventLabels[event.action] || "定制状态更新"
                    }}</strong>
                    <p class="preserve">{{ event.message }}</p>
                    <small class="secondary">{{
                      formatDate(event.created_at)
                    }}</small></a-timeline-item
                  ></a-timeline
                ></a-col
              ><a-col :xs="24" :lg="12"
                ><h3>管理员操作记录</h3>
                <a-timeline
                  ><a-timeline-item v-for="event in d.audit" :key="event.id"
                    ><strong
                      >{{ event.actor }} ·
                      {{ eventLabels[event.action] || event.action }}</strong
                    >
                    <p class="preserve">{{ event.details.message }}</p>
                    <small class="secondary"
                      >{{ formatDate(event.created_at) }} · 修订
                      {{ event.details.revision }}</small
                    ></a-timeline-item
                  ></a-timeline
                ></a-col
              ></a-row
            >
          </a-tab-pane>
        </a-tabs>
      </template>
    </a-drawer>
    <a-modal
      :open="!!w.dialog.value"
      :title="w.dialog.value?.title"
      :confirm-loading="w.actionBusy.value"
      :mask-closable="false"
      @ok="w.confirmDialog"
      @cancel="w.dialog.value = null"
      ><template v-if="w.dialog.value"
        ><p>本次说明只用于此操作，提交后用户可以看到。</p>
        <a-alert
          v-if="w.error.value"
          :message="w.error.value"
          type="error"
          show-icon
          class="feedback"
        /><a-textarea
          v-model:value="w.dialog.value.message"
          :rows="5"
          :maxlength="3000"
          show-count
          placeholder="请填写具体说明或原因"
        />
        <p v-if="w.dialog.value.action === 'withdraw'" class="secondary spaced">
          撤回后停止新的下载授权，已经下载的文件无法收回。
        </p></template
      ></a-modal
    >
    <a-modal
      :open="!!w.preview.value"
      title="成品页面预览"
      :footer="null"
      :width="1000"
      @cancel="w.preview.value = undefined"
      ><img
        :src="w.preview.value"
        alt="成品页面"
        style="max-width: 100%; max-height: 78vh; display: block; margin: auto"
    /></a-modal>
  </main>
</template>
<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from "vue";
import dayjs, { type Dayjs } from "dayjs";
import { onBeforeRouteLeave } from "vue-router";
import {
  useCustomizationWorkspace,
  post,
} from "../features/customizations/useCustomizationWorkspace";
import {
  statusLabels,
  jobLabels,
  eventLabels,
  briefLabels,
  selectedPhotos,
  selectedContent,
  reviewFor,
  reviewProblem,
  canReview,
  notificationText,
} from "../features/customizations/domain";
import type { Delivery, Photo } from "../features/customizations/types";
import PhotoGrid from "../features/customizations/PhotoGrid.vue";
const w = useCustomizationWorkspace(),
  d = computed(() => w.current.value),
  e = computed(() => w.editor.value),
  previewCandidate = ref<string>();
onBeforeRouteLeave(() => w.permitLeave());
const buckets = [
  { key: "submitted", title: "待受理" },
  { key: "pending_info", title: "新资料待确认" },
  { key: "revision_requested", title: "待修改" },
  { key: "ready_for_review", title: "待验收交付" },
  { key: "cancellation", title: "取消申请" },
  { key: "overdue", title: "已逾期" },
];
const columns = [
  { title: "主题 / 单号", key: "title", width: 230 },
  { title: "用户", key: "user", width: 140 },
  { title: "状态与待办", key: "status", width: 190 },
  { title: "负责人", key: "assigned", width: 120 },
  { title: "预计交付", key: "due", width: 180 },
  { title: "更新时间", key: "updated", width: 180 },
  { title: "操作", key: "open", width: 120 },
];
const jobColumns = [
  { title: "创建时间", key: "created" },
  { title: "状态", key: "status" },
  { title: "制作依据", dataIndex: "submission_id" },
  { title: "错误说明", dataIndex: "error" },
  { title: "操作", key: "action" },
];
const viewedSubmission = computed(() =>
    d.value?.submissions.find((s) => s.id === e.value.submission),
  ),
  acceptedSubmission = computed(() =>
    d.value?.submissions.find((s) => s.id === d.value?.accepted_submission_id),
  );
const content = computed(() =>
    d.value ? selectedContent(d.value, e.value) : { title: "", brief: {} },
  ),
  photos = computed(() => (d.value ? selectedPhotos(d.value, e.value) : []));
const candidates = computed(
    () =>
      d.value?.deliveries.filter((c) => c.status === "ready_for_review") ?? [],
  ),
  published = computed(
    () =>
      d.value?.deliveries
        .filter((c) => c.status !== "ready_for_review")
        .sort(
          (a, b) => (b.published_number ?? 0) - (a.published_number ?? 0),
        ) ?? [],
  );
const reminderCooling = computed(
  () =>
    !!d.value?.reminder_available_at &&
    dayjs(d.value.reminder_available_at).isAfter(dayjs()),
);
const toolCommand = computed(() =>
  d.value && e.value.submission
    ? `python custom_workflow.py fetch-brief --request-id ${d.value.id} --submission-id ${e.value.submission} --output custom-work/${d.value.id}/submission-${e.value.submission}`
    : "请先选择一个提交版本",
);
function formatDate(raw?: string | null) {
  return raw ? dayjs(raw).format("YYYY-MM-DD HH:mm") : "未设置";
}
function statusColor(s: string) {
  return (
    {
      submitted: "blue",
      in_production: "cyan",
      needs_info: "orange",
      revision_requested: "orange",
      delivered: "green",
      cancelled: "default",
      rejected: "red",
    } as Record<string, string>
  )[s];
}
function selectTask(key: string) {
  w.task.value = w.task.value === key ? "" : key;
  void w.load(true);
}
function clearFilters() {
  w.q.value = "";
  w.status.value = "";
  w.task.value = "";
  w.assigned.value = undefined;
  void w.load(true);
}
function dateChanged(value: Dayjs | null) {
  e.value.due = value?.toISOString() ?? null;
}
function adoptServer() {
  if (!d.value) return;
  e.value.due = d.value.due_at;
  e.value.internalNote = d.value.internal_note;
  w.conflict.value = false;
}
function candidatePhotos(c: Delivery): Photo[] {
  return (
    d.value?.submissions.find((s) => s.id === c.submission_id)
      ?.resolved_assets ?? []
  );
}
function submissionLabel(id: number) {
  const sub = d.value?.submissions.find((s) => s.id === id);
  return sub ? "提交 #" + sub.number : "历史提交";
}
function noticeTitle(scene: string) {
  return eventLabels[scene.split(".").at(-1) ?? ""] ?? "定制进度提醒";
}
async function copyCommand() {
  try {
    await navigator.clipboard.writeText(toolCommand.value);
    w.success.value = "PSD 工具下载命令已复制";
  } catch {
    w.error.value = "无法复制，请手动复制下方命令";
  }
}
function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0];
  input.value = "";
  if (file) void w.prepare(file);
}
// Stream a complete source set directly from OSS into a user-selected directory.
interface WritableFile {
  write(chunk: Uint8Array): Promise<void>;
  close(): Promise<void>;
  abort(): Promise<void>;
}
interface Folder {
  getFileHandle(
    name: string,
    options: { create: boolean },
  ): Promise<{ createWritable(): Promise<WritableFile> }>;
}
const downloadBusy = ref(false),
  downloadStatus = ref("");
let downloadAbort: AbortController | undefined;
async function downloadPhotos() {
  if (!d.value || !e.value.submission || downloadBusy.value) return;
  const picker = (
    window as unknown as { showDirectoryPicker?: () => Promise<Folder> }
  ).showDirectoryPicker;
  if (!picker) {
    downloadStatus.value =
      "此浏览器不支持目录写入，请使用上方 PSD 工具命令一次下载全部资料。";
    return;
  }
  const id = d.value.id,
    sub = e.value.submission;
  downloadBusy.value = true;
  downloadStatus.value = "";
  downloadAbort = new AbortController();
  const signal = downloadAbort.signal;
  try {
    const dir = await picker();
    if (signal.aborted) return;
    const brief = await post<{ assets: Photo[] }>(
      `requests/${id}/source-export/`,
      { submission_id: sub },
    );
    for (const [index, p] of brief.assets.entries()) {
      if (
        signal.aborted ||
        w.current.value?.id !== id ||
        e.value.submission !== sub
      )
        break;
      downloadStatus.value = `正在下载 ${index + 1}/${brief.assets.length}`;
      const response = await fetch(p.url!, { signal });
      if (!response.ok || !response.body)
        throw new Error("照片下载失败，请更新链接后重试");
      const file = await dir.getFileHandle(
          `photo-${index + 1}-${p.id}.${p.mime === "image/png" ? "png" : "jpg"}`,
          { create: true },
        ),
        out = await file.createWritable(),
        reader = response.body.getReader();
      try {
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          await out.write(chunk.value);
        }
        await out.close();
      } catch (err) {
        await out.abort();
        throw err;
      }
    }
    if (!signal.aborted)
      downloadStatus.value = `已下载 ${brief.assets.length} 张照片到所选目录`;
  } catch (err) {
    if (!signal.aborted)
      downloadStatus.value = err instanceof Error ? err.message : "下载已取消";
  } finally {
    downloadBusy.value = false;
  }
}
watch(
  () => [w.current.value?.id, e.value.submission],
  () => {
    previewCandidate.value = undefined;
    downloadAbort?.abort();
    downloadStatus.value = "";
  },
);
onBeforeUnmount(() => downloadAbort?.abort());
</script>
<style scoped>
.customizations {
  max-width: 1680px;
  margin: auto;
}
.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
}
.page-heading h1 {
  font-size: 25px;
  margin: 0 0 8px;
}
.page-heading p,
.secondary {
  color: #7a8393;
}
.task-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.task-card {
  border: 1px solid #e4e8ef;
  border-radius: 10px;
  background: #fafbfc;
  padding: 16px 18px;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.task-card strong {
  font-size: 26px;
  color: #24334b;
}
.task-card.active {
  border-color: #1677ff;
  background: #edf5ff;
}
.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.block {
  display: block;
}
.flags {
  margin-top: 5px;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 14px;
  margin-top: 20px;
}
.workspace-head {
  position: sticky;
  top: -24px;
  z-index: 5;
  background: #fff;
  padding: 12px 0 18px;
  border-bottom: 1px solid #edf0f5;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
}
.workspace-head h2 {
  font-size: 23px;
  margin: 7px 0 12px;
}
.eyebrow {
  font-size: 12px;
  color: #748197;
}
.next-step {
  flex-basis: 100%;
  background: #f0f6ff;
  padding: 12px 16px;
  border-radius: 8px;
  display: flex;
  gap: 14px;
  color: #274b7c;
}
.feedback {
  margin: 12px 0;
}
.section-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  margin: 8px 0 16px;
}
.section-head h3 {
  margin-bottom: 6px;
}
.basis-strip {
  display: flex;
  gap: 24px;
  padding: 12px 0 20px;
  font-weight: 600;
}
.preserve {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.spaced {
  margin-top: 20px;
}
.overdue {
  color: #cf1322;
}
.archive-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 18px;
  background: #f8fafc;
  margin-top: 15px;
  border-radius: 8px;
}
.page-previews {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}
.page-previews img {
  width: 100%;
  height: 190px;
  object-fit: contain;
  background: #f4f6f9;
  cursor: zoom-in;
}
.opening {
  display: block;
  padding: 50px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 7px;
}
.workspace-tabs :deep(.ant-tabs-nav) {
  background: #fff;
}
@media (max-width: 1000px) {
  .task-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .section-head {
    align-items: stretch;
    flex-direction: column;
  }
  .page-previews {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 550px) {
  .task-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .page-heading {
    align-items: flex-start;
  }
  .basis-strip {
    flex-direction: column;
    gap: 5px;
  }
  .filters {
    flex-direction: column;
  }
}
</style>
