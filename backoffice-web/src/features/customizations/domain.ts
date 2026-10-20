import type { Detail, Editor, Delivery, Photo, Notice } from "./types";
export const statusLabels: Record<string, string> = {
  draft: "草稿",
  submitted: "待受理",
  needs_info: "待用户补充",
  in_production: "制作中",
  delivered: "已交付，待确认",
  revision_requested: "待修改",
  completed: "已完成",
  cancelled: "已取消",
  rejected: "无法制作",
};
export const jobLabels: Record<string, string> = {
  uploading: "等待上传完成",
  queued: "等待成品处理",
  processing: "正在处理成品",
  ready: "候选已准备好",
  failed: "处理失败",
  abandoned: "已结束",
};
export const eventLabels: Record<string, string> = {
  submitted: "用户提交需求",
  info_requested: "要求补充资料",
  info_submitted: "用户补充资料",
  accepted: "已受理",
  basis_updated: "已确认新的制作依据",
  revision_requested: "用户提出修改",
  revision_started: "开始修订",
  delivered: "首次交付",
  redelivered: "新版交付",
  completed: "用户确认完成",
  due_changed: "预计日期已调整",
  production_updated: "保存进度",
  cancelled: "需求已取消",
  rejected: "暂无法制作",
  pending_reminder: "发送待办提醒",
  cancellation_requested: "用户申请取消",
  delivery_withdrawn: "撤回交付",
  delivery_rolled_back: "调整当前交付",
  assign: "转交负责人",
  production: "保存制作进度",
  accept: "确认制作依据",
  "request-info": "要求补充",
  deliver: "交付",
  withdraw: "撤回交付",
  rollback: "调整当前交付",
  reject: "拒绝需求",
  cancel: "取消需求",
  remind: "发送待办提醒",
};
export const briefLabels: Record<string, string> = {
  description: "想记录的故事",
  category: "场景分类",
  style: "风格偏好",
  important_text: "必须保留的文字",
  story_order: "故事顺序与页数偏好",
  avoid: "不希望出现的内容",
  page_preference: "页数偏好",
};
export const reasonLabels: Record<string, string> = {
  no_push_enabled_device: "用户没有可接收推送的设备",
  topic_opt_out: "用户关闭了定制通知",
  quiet_hours: "处于免打扰时段，稍后发送",
  deferred_quiet_hours: "处于免打扰时段，稍后发送",
  already_seen: "用户已查看，跳过推送",
  superseded: "已有更新替代该通知",
  expired: "通知已过期",
  temporary_apns_failure: "推送暂时失败，等待重试",
  unavailable: "需求或账号已不可用",
  Unregistered: "设备推送地址已失效",
};
export function newEditor(d: Detail): Editor {
  return {
    submission: d.latest_submission_id ?? undefined,
    due: d.due_at,
    internalNote: d.internal_note,
    assignedTo: d.assigned_to ?? undefined,
    reviews: {},
    section: "materials",
  };
}
export function reviewFor(e: Editor, id: string) {
  return (
    e.reviews[id] ??
    (e.reviews[id] = { used: [], reviewed: false, message: "" })
  );
}
export function selectedPhotos(d: Detail, e: Editor): Photo[] {
  const sub = d.submissions.find((s) => s.id === e.submission);
  return sub ? sub.resolved_assets : d.assets;
}
export function selectedContent(d: Detail, e: Editor) {
  return (
    d.submissions.find((s) => s.id === e.submission)?.snapshot ?? {
      title: d.title,
      brief: d.brief,
    }
  );
}
export function productionDirty(e: Editor, d: Detail) {
  return e.due !== d.due_at || e.internalNote !== d.internal_note;
}
export function hasEdits(e: Editor, d: Detail) {
  return (
    productionDirty(e, d) ||
    Object.values(e.reviews).some(
      (r) => r.used.length || r.reviewed || r.message,
    )
  );
}
export function canReview(d: Detail, c: Delivery) {
  return (
    d.allowed_actions.includes("deliver") &&
    c.status === "ready_for_review" &&
    c.submission_id === d.accepted_submission_id
  );
}
export function reviewProblem(d: Detail, c: Delivery, e: Editor) {
  if (!canReview(d, c)) return "此候选的制作依据已过期，或需求当前不允许交付";
  const r = reviewFor(e, c.id);
  if (!r.reviewed) return "请先完成该候选的 iOS 视觉与编辑验收";
  const photos =
    d.submissions.find((s) => s.id === c.submission_id)?.snapshot.assets ?? [];
  if (photos.some((p) => p.must_use && !r.used.includes(p.id)))
    return "请勾选此版本实际使用的全部必用照片";
  return "";
}
export function notificationText(n: Notice) {
  if (n.seen) return "用户已查看该更新";
  const last = n.deliveries.at(-1),
    box = n.outbox[0];
  if (last?.status === "accepted") return "APNs 已受理，用户是否看到尚未知";
  const reason = box?.last_error || last?.error_message;
  if (reason) return reasonLabels[reason] ?? "发送异常，请查看完整投递记录";
  return (
    (
      {
        pending: "等待发送",
        processing: "正在发送",
        failed: "发送失败",
        cancelled: "已跳过",
        completed: "投递处理结束",
        expired: "已过期",
      } as Record<string, string>
    )[n.status] ?? "等待处理"
  );
}
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object")
    return (
      "{" +
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => JSON.stringify(k) + ":" + canonical(v))
        .join(",") +
      "}"
    );
  return JSON.stringify(value) ?? "null";
}
export class SessionGate {
  private version = 0;
  change() {
    return ++this.version;
  }
  current(version: number) {
    return this.version === version;
  }
}
