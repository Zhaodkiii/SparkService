import {
  ref,
  computed,
  onMounted,
  onActivated,
  onDeactivated,
  onBeforeUnmount,
} from "vue";
import OSS from "ali-oss";
import { sha256 } from "hash-wasm";
import { Modal } from "ant-design-vue";
import http, { ApiError } from "../../api/http";
import { useAuthStore } from "../../stores/auth";
import {
  newEditor,
  productionDirty,
  hasEdits,
  SessionGate,
  canonical,
  reviewFor,
} from "./domain";
import type {
  Detail,
  Row,
  Editor,
  ArchiveInfo,
  UploadSession,
  Job,
} from "./types";

const base = "/api/admin/v1/diary-customizations/";
export const get = <T>(p: string) =>
  http.get(base + p) as unknown as Promise<T>;
export const post = <T>(p: string, data: unknown, key?: string) =>
  http.post(
    base + p,
    data,
    key ? { headers: { "Idempotency-Key": key } } : undefined,
  ) as unknown as Promise<T>;
const emptyEditor = (): Editor => ({
  due: null,
  internalNote: "",
  reviews: {},
  section: "materials",
});
export function useCustomizationWorkspace() {
  const auth = useAuthStore(),
    gate = new SessionGate();
  const rows = ref<Row[]>([]),
    summary = ref<Record<string, number>>({}),
    q = ref(""),
    status = ref(""),
    task = ref(""),
    assigned = ref<number>(),
    page = ref(1),
    next = ref<number | null>(null);
  const listLoading = ref(false),
    listError = ref(""),
    operators = ref<{ id: number; name: string }[]>([]);
  const current = ref<Detail | null>(null),
    opening = ref(false),
    editor = ref<Editor>(emptyEditor()),
    error = ref(""),
    success = ref(""),
    conflict = ref(false),
    actionBusy = ref(false);
  const archive = ref<File>(),
    archiveInfo = ref<ArchiveInfo>(),
    hashProgress = ref(0),
    uploadProgress = ref(0),
    uploadStage = ref(""),
    transferBusy = ref(false),
    activeJob = ref<string>(),
    preview = ref<string>();
  const dialog = ref<{
    action: string;
    title: string;
    message: string;
    deliveryID?: string;
  } | null>(null);
  let session = 0,
    listSequence = 0,
    polling = false,
    active = true,
    worker: Worker | undefined,
    client: OSS | undefined;
  let hashReject: ((e: Error) => void) | undefined,
    pollTimer: ReturnType<typeof setTimeout> | undefined,
    wake: (() => void) | undefined;
  const pending = ref<{
    action: string;
    body: Record<string, unknown>;
    fingerprint: string;
    key: string;
  } | null>(null);
  const pendingKey = () =>
    `custom-pending:${auth.user?.id}:${current.value?.id}`;
  const dirty = computed(
    () => !!current.value && hasEdits(editor.value, current.value),
  );
  const productionChanged = computed(
    () => !!current.value && productionDirty(editor.value, current.value),
  );
  const allowed = (name: string) =>
    current.value?.allowed_actions.includes(name) ?? false;
  const isCurrent = (stamp: number, id: string) =>
    active && gate.current(stamp) && current.value?.id === id;
  function stop() {
    worker?.terminate();
    worker = undefined;
    hashReject?.(new Error("已停止文件准备"));
    hashReject = undefined;
    client?.cancel();
    client = undefined;
    clearTimeout(pollTimer);
    wake?.();
    wake = undefined;
    polling = false;
    transferBusy.value = false;
  }
  function reset() {
    session = gate.change();
    stop();
    archive.value = undefined;
    archiveInfo.value = undefined;
    hashProgress.value = 0;
    uploadProgress.value = 0;
    uploadStage.value = "";
    activeJob.value = undefined;
    preview.value = undefined;
    editor.value = emptyEditor();
    dialog.value = null;
    pending.value = null;
    error.value = "";
    success.value = "";
    conflict.value = false;
    actionBusy.value = false;
  }
  async function load(resetPage = false) {
    if (resetPage) page.value = 1;
    const seq = ++listSequence;
    listLoading.value = true;
    listError.value = "";
    const params = new URLSearchParams({
      page: String(page.value),
      q: q.value,
      status: status.value,
      task: task.value,
    });
    if (assigned.value) params.set("assigned_to", String(assigned.value));
    try {
      const r = await get<{
        results: Row[];
        next_page: number | null;
        summary: Record<string, number>;
      }>(`requests/?${params}`);
      if (seq !== listSequence) return;
      rows.value = r.results;
      next.value = r.next_page;
      summary.value = r.summary;
    } catch (e) {
      if (seq === listSequence) listError.value = describe(e);
    } finally {
      if (seq === listSequence) listLoading.value = false;
    }
  }
  async function permitLeave() {
    if (
      !dirty.value &&
      !dialog.value?.message &&
      !transferBusy.value &&
      !pending.value
    )
      return true;
    return new Promise<boolean>((resolve) =>
      Modal.confirm({
        title: "离开当前制作需求？",
        content: pending.value
          ? "有一次操作结果尚未确认。可重新打开本需求核对结果。"
          : "未保存的编辑和本次验收勾选将清空；上传会暂停，重新选择同一文件可继续。",
        okText: "离开并清空",
        cancelText: "继续编辑",
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      }),
    );
  }
  async function open(id: string) {
    if (current.value?.id === id) {
      await refresh();
      return;
    }
    if (!(await permitLeave())) return;
    reset();
    current.value = null;
    opening.value = true;
    const stamp = session;
    try {
      const d = await get<Detail>(`requests/${id}/`);
      if (!gate.current(stamp) || !active) return;
      current.value = d;
      editor.value = newEditor(d);
      const saved = sessionStorage.getItem(pendingKey());
      if (saved) {
        error.value = "上次有一次操作结果未确认，正在核对…";
        const p = JSON.parse(saved) as { key: string; action: string };
        const r = await get<{ applied: boolean }>(
          `requests/${id}/operations/?key=${encodeURIComponent(p.key)}`,
        );
        if (!isCurrent(stamp, id)) return;
        error.value = r.applied
          ? ""
          : "上次请求未查到成功记录，请核对最新状态后重试";
        if (r.applied) {
          sessionStorage.removeItem(pendingKey());
          success.value = "已核对：上次操作已成功";
        }
      }
      void poll(stamp, id);
    } catch (e) {
      if (gate.current(stamp)) error.value = describe(e);
    } finally {
      if (gate.current(stamp)) opening.value = false;
    }
  }
  async function close() {
    if (!(await permitLeave())) return;
    reset();
    current.value = null;
  }
  function apply(d: Detail) {
    const old = current.value;
    if (!old || old.id !== d.id) return;
    if (d.revision < old.revision) return;
    // Server refreshes update facts only. Preserve local notes/date, selected snapshot and reviews.
    if (editor.value.due === old.due_at) editor.value.due = d.due_at;
    if (editor.value.internalNote === old.internal_note)
      editor.value.internalNote = d.internal_note;
    if (editor.value.assignedTo === (old.assigned_to ?? undefined))
      editor.value.assignedTo = d.assigned_to ?? undefined;
    if (old.accepted_submission_id !== d.accepted_submission_id) {
      editor.value.reviews = {};
      archiveInfo.value = undefined;
      archive.value = undefined;
    }
    current.value = d;
  }
  async function refresh() {
    if (!current.value) return;
    const stamp = session,
      id = current.value.id;
    try {
      const d = await get<Detail>(`requests/${id}/`);
      if (isCurrent(stamp, id)) apply(d);
    } catch (e) {
      if (isCurrent(stamp, id)) error.value = describe(e);
    }
  }
  async function act(action: string, data: Record<string, unknown> = {}) {
    if (!current.value || actionBusy.value) return false;
    const stamp = session,
      id = current.value.id;
    actionBusy.value = true;
    error.value = "";
    success.value = "";
    const fingerprint = canonical({ action, data });
    try {
      if (pending.value && pending.value.fingerprint !== fingerprint)
        throw new Error("请先核对上次未确认操作的结果，再执行其他操作");
      const body = pending.value?.body ?? {
        expected_revision: current.value.revision,
        ...data,
      };
      const key =
        pending.value?.key ??
        "admin-" +
          (await sha256(canonical({ actor: auth.user?.id, id, action, body })));
      if (!isCurrent(stamp, id)) return false;
      pending.value = { action, body, fingerprint, key };
      sessionStorage.setItem(pendingKey(), JSON.stringify({ key, action }));
      const d = await post<Detail>(`requests/${id}/${action}/`, body, key);
      if (!isCurrent(stamp, id)) return false;
      apply(d);
      if (action === "production") {
        editor.value.due = d.due_at;
        editor.value.internalNote = d.internal_note;
        conflict.value = false;
      }
      if (action === "assign")
        editor.value.assignedTo = d.assigned_to ?? undefined;
      if (action === "accept")
        editor.value.submission = d.accepted_submission_id ?? undefined;
      if (data.delivery_id) {
        delete editor.value.reviews[String(data.delivery_id)];
      }
      sessionStorage.removeItem(pendingKey());
      pending.value = null;
      conflict.value = false;
      success.value = "操作已完成，最新状态已同步";
      void load();
      return true;
    } catch (e) {
      if (!isCurrent(stamp, id)) return false;
      if (e instanceof ApiError && e.status && e.status < 500) {
        pending.value = null;
        sessionStorage.removeItem(pendingKey());
        error.value = describe(e);
        if (e.status === 409) {
          conflict.value = true;
          await refresh();
        }
        return false;
      }
      if (pending.value) {
        try {
          const r = await get<{ applied: boolean }>(
            `requests/${id}/operations/?key=${encodeURIComponent(pending.value.key)}`,
          );
          if (!isCurrent(stamp, id)) return false;
          if (r.applied) {
            sessionStorage.removeItem(pendingKey());
            pending.value = null;
            await refresh();
            if (!isCurrent(stamp, id)) return false;
            success.value = "已核对：操作已成功，无需重复执行";
            void load();
            return true;
          }
        } catch {
          /* Keep the original key and body for a safe retry. */
        }
        error.value =
          "未能确认操作结果。输入已保留，请点“重试上次操作”或“核对最新状态”。";
      } else error.value = describe(e);
      return false;
    } finally {
      if (isCurrent(stamp, id)) actionBusy.value = false;
    }
  }
  async function retryAction() {
    const p = pending.value;
    if (!p) return;
    const data = { ...p.body };
    delete data.expected_revision;
    await act(p.action, data);
  }
  async function reconcile() {
    if (!current.value) return;
    const stamp = session,
      id = current.value.id;
    try {
      if (pending.value) {
        const r = await get<{ applied: boolean }>(
          `requests/${id}/operations/?key=${encodeURIComponent(pending.value.key)}`,
        );
        if (!isCurrent(stamp, id)) return;
        if (r.applied) {
          sessionStorage.removeItem(pendingKey());
          pending.value = null;
          error.value = "";
          success.value = "上次操作已成功";
        }
      }
      await refresh();
    } catch (e) {
      if (isCurrent(stamp, id)) error.value = describe(e);
    }
  }
  function showDialog(action: string, title: string, deliveryID?: string) {
    dialog.value = { action, title, message: "", deliveryID };
  }
  async function confirmDialog() {
    const d = dialog.value;
    if (!d) return;
    if (!d.message.trim()) {
      error.value = "请填写本次操作的说明或原因";
      return;
    }
    if (
      await act(d.action, {
        message: d.message,
        ...(d.deliveryID ? { delivery_id: d.deliveryID } : {}),
      })
    )
      dialog.value = null;
  }
  async function deliver(id: string) {
    const r = reviewFor(editor.value, id);
    await act("deliver", {
      delivery_id: id,
      used_asset_ids: r.used,
      ios_reviewed: r.reviewed,
      message: r.message,
    });
  }
  async function prepare(file: File) {
    if (!current.value || transferBusy.value) return;
    const stamp = session,
      id = current.value.id;
    archive.value = file;
    archiveInfo.value = undefined;
    transferBusy.value = true;
    uploadStage.value = "正在读取清单与计算摘要";
    hashProgress.value = 0;
    error.value = "";
    try {
      const info = await new Promise<ArchiveInfo>((resolve, reject) => {
        hashReject = reject;
        worker = new Worker(new URL("./archive.worker.ts", import.meta.url), {
          type: "module",
        });
        worker.onmessage = (e) => {
          if (!isCurrent(stamp, id)) return;
          if (e.data.error) reject(new Error(e.data.error));
          else if (e.data.info) resolve(e.data.info);
          else hashProgress.value = e.data.progress;
        };
        worker.onerror = () => reject(new Error("文件准备失败，请重新选择"));
        worker.postMessage({ file, requestID: id });
      });
      if (isCurrent(stamp, id)) {
        archiveInfo.value = info;
        uploadStage.value = "文件已准备，可开始上传";
      }
    } catch (e) {
      if (isCurrent(stamp, id)) {
        error.value = describe(e);
        uploadStage.value = "文件准备已停止";
      }
    } finally {
      if (isCurrent(stamp, id)) {
        worker?.terminate();
        worker = undefined;
        hashReject = undefined;
        transferBusy.value = false;
      }
    }
  }
  async function upload() {
    if (
      !current.value ||
      !archive.value ||
      !archiveInfo.value ||
      transferBusy.value
    )
      return;
    const stamp = session,
      id = current.value.id,
      file = archive.value,
      info = archiveInfo.value,
      basis = current.value.accepted_submission_id;
    if (info.requestID !== id || !allowed("upload")) return;
    transferBusy.value = true;
    error.value = "";
    uploadProgress.value = 0;
    uploadStage.value = "正在申请上传会话";
    try {
      const r = await post<UploadSession>(`requests/${id}/delivery-uploads/`, {
        size: file.size,
        sha256: info.sha,
        submission_id: basis,
      });
      if (!isCurrent(stamp, id)) return;
      activeJob.value = r.id;
      if (r.credentials) {
        const c = r.credentials,
          checkpointKey = `custom-upload:${auth.user?.id}:${id}:${basis}:${info.sha}`;
        client = new OSS({
          ...c,
          refreshSTSToken: async () => {
            if (!isCurrent(stamp, id)) throw new Error("需求已切换");
            const v = await post<UploadSession>(`uploads/${r.id}/refresh/`, {});
            if (!v.credentials) throw new Error("会话已结束");
            return v.credentials;
          },
          refreshSTSTokenInterval: 300000,
        });
        const saved = sessionStorage.getItem(checkpointKey);
        let checkpoint;
        try {
          checkpoint = saved ? JSON.parse(saved) : undefined;
        } catch {
          sessionStorage.removeItem(checkpointKey);
        }
        uploadStage.value = "正在直传 OSS";
        await client.multipartUpload(c.key, file, {
          checkpoint,
          partSize: 8 * 1024 * 1024,
          parallel: 3,
          progress: async (p, c) => {
            if (!isCurrent(stamp, id)) return;
            uploadProgress.value = p;
            sessionStorage.setItem(checkpointKey, JSON.stringify(c));
          },
        });
        if (!isCurrent(stamp, id)) return;
        uploadStage.value = "正在登记成品包";
        await post(`uploads/${r.id}/complete/`, {});
        sessionStorage.removeItem(checkpointKey);
      }
      if (!isCurrent(stamp, id)) return;
      if (["failed", "abandoned"].includes(r.status)) {
        uploadStage.value = "现有成品任务未完成，请查看任务错误后重试处理";
      } else uploadStage.value = "上传已结束，正在等待候选处理";
      await refresh();
      void poll(stamp, id);
    } catch (e) {
      if (isCurrent(stamp, id)) {
        error.value = describe(e);
        uploadStage.value = "上传已暂停或失败，可重新选择同一文件继续";
      }
    } finally {
      if (isCurrent(stamp, id)) {
        transferBusy.value = false;
        client = undefined;
      }
    }
  }
  function pauseUpload() {
    worker?.terminate();
    worker = undefined;
    hashReject?.(new Error("已停止文件准备"));
    hashReject = undefined;
    client?.cancel();
    uploadStage.value = "上传已暂停，选择同一文件后可继续";
  }
  async function poll(stamp: number, id: string) {
    if (polling || !isCurrent(stamp, id)) return;
    polling = true;
    try {
      while (isCurrent(stamp, id)) {
        const pendingJobs =
          current.value?.jobs.filter(
            (j) =>
              j.kind === "delivery" &&
              ["queued", "processing"].includes(j.status),
          ) ?? [];
        if (!pendingJobs.length) return;
        await new Promise<void>((resolve) => {
          wake = resolve;
          pollTimer = setTimeout(resolve, 3000);
        });
        wake = undefined;
        if (!isCurrent(stamp, id)) return;
        try {
          const d = await get<Detail>(`requests/${id}/`);
          if (!isCurrent(stamp, id)) return;
          apply(d);
          const job = d.jobs.find((j) => j.id === activeJob.value);
          if (job?.status === "ready") {
            uploadStage.value = "成品候选已就绪，请逐版本验收后交付";
            success.value = uploadStage.value;
          } else if (job?.status === "failed") {
            uploadStage.value = "成品处理失败";
            error.value = job.error || "请查看任务错误并重试";
          }
        } catch (e) {
          if (isCurrent(stamp, id)) {
            error.value =
              "成品状态获取失败，已停止自动刷新；点击刷新可继续。" +
              describe(e);
          }
          return;
        }
      }
    } finally {
      if (gate.current(stamp)) polling = false;
    }
  }
  async function retryJob(j: Job) {
    if (!current.value || actionBusy.value) return;
    const stamp = session,
      id = current.value.id;
    actionBusy.value = true;
    try {
      await post(`uploads/${j.id}/retry/`, {});
      if (!isCurrent(stamp, id)) return;
      activeJob.value = j.id;
      await refresh();
      success.value = "任务已重新提交";
      void poll(stamp, id);
    } catch (e) {
      if (isCurrent(stamp, id)) error.value = describe(e);
    } finally {
      if (isCurrent(stamp, id)) actionBusy.value = false;
    }
  }
  async function refreshAll() {
    await refresh();
    if (current.value) void poll(session, current.value.id);
  }
  async function exportBrief() {
    if (!current.value || !editor.value.submission) return;
    const stamp = session,
      id = current.value.id,
      submissionID = editor.value.submission;
    try {
      const data = await post(`requests/${id}/source-export/`, {
        submission_id: submissionID,
      });
      if (!isCurrent(stamp, id)) return;
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `custom-${id}-submission-${submissionID}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      success.value = "制作清单已导出，下载链接有效 10 分钟";
    } catch (e) {
      if (isCurrent(stamp, id)) error.value = describe(e);
    }
  }
  function beforeUnload(e: BeforeUnloadEvent) {
    if (dirty.value || transferBusy.value || pending.value) {
      e.preventDefault();
      e.returnValue = "";
    }
  }
  onMounted(() => {
    void load();
    void get<{ results: { id: number; name: string }[] }>("operators/")
      .then((r) => (operators.value = r.results))
      .catch(() => {});
    window.addEventListener("beforeunload", beforeUnload);
  });
  onActivated(() => {
    active = true;
    if (current.value) {
      if (pending.value) void reconcile();
      else void refreshAll();
    }
  });
  onDeactivated(() => {
    active = false;
    session = gate.change();
    stop();
    actionBusy.value = false;
    opening.value = false;
  });
  onBeforeUnmount(() => {
    active = false;
    reset();
    window.removeEventListener("beforeunload", beforeUnload);
  });
  return {
    rows,
    summary,
    q,
    status,
    task,
    assigned,
    page,
    next,
    listLoading,
    listError,
    operators,
    current,
    opening,
    editor,
    error,
    success,
    conflict,
    actionBusy,
    archive,
    archiveInfo,
    hashProgress,
    uploadProgress,
    uploadStage,
    transferBusy,
    activeJob,
    preview,
    dialog,
    pending,
    dirty,
    productionChanged,
    allowed,
    load,
    open,
    close,
    permitLeave,
    refresh: refreshAll,
    act,
    retryAction,
    reconcile,
    showDialog,
    confirmDialog,
    deliver,
    prepare,
    upload,
    pauseUpload,
    retryJob,
    exportBrief,
  };
}
function describe(e: unknown) {
  if (e instanceof Error && e.message === "Network Error")
    return "网络请求未完成，请检查服务连接和跨域配置；本次输入已保留";
  return e instanceof Error ? e.message : "操作失败，请稍后重试";
}
