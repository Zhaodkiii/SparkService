"use client";

import { Activity, CircleAlert, CircleCheck, Clock3, Database, Loader2, Radio, Wrench, X, XCircle } from "lucide-react";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { runStatusLabel } from "@/lib/event-reducer";
import { CHAT_TOOL_UI_ENABLED } from "@/lib/feature-flags";
import { projectToolActivity } from "@/lib/chat/activity-projection";
import { orderedToolActivities } from "@/lib/tools/tool-activity-selectors";
import type { ToolActivityDTO } from "@/types/tool";

const EVENT_LABELS: Record<string, string> = {
  "run.queued": "请求已进入队列",
  "run.started": "开始生成回答",
  "assistant.status": "生成状态更新",
  "block.created": "创建回答内容",
  "block.delta": "接收流式内容",
  "block.updated": "更新回答内容",
  "block.completed": "回答内容完成",
  "usage.final": "用量统计完成",
  "run.done": "本轮对话结束",
  "tool.call.requested": "准备调用服务工具",
  "tool.call.started": "工具开始执行",
  "tool.result": "工具返回结果",
  "tool.call.cancelled": "工具调用已取消",
};

function toolIcon(status: ToolActivityDTO["status"]) {
  if (status === "running" || status === "requested") return <Loader2 size={13} className="tool-disclosure__spin" />;
  if (status === "completed") return <CircleCheck size={13} />;
  if (status === "failed") return <CircleAlert size={13} />;
  return <XCircle size={13} />;
}

function ToolActivityRow({ activity }: { activity: ToolActivityDTO }) {
  const view = projectToolActivity(activity);
  const time = activity.finished_at ?? activity.started_at;
  return <div className={`activity-event activity-event--tool tool-disclosure--${view.tone}`}>
    <span className={`activity-event__dot activity-event__dot--${view.tone}`}>{toolIcon(activity.status)}</span>
    <div>
      <strong>{view.errorLine ? `${view.displayName} · ${view.errorLine}` : view.resultLine ? `${view.displayName} · ${view.resultLine}` : `${view.displayName} · ${view.statusLabel}`}</strong>
      {time ? <time>{new Date(time).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time> : null}
    </div>
  </div>;
}

export function SessionActivityPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const run = useOptionalRunControl();
  const usage = run?.run ? run.state.usageByRun[run.run.id] : null;
  const toolActivities = run?.run ? orderedToolActivities(run.state, run.run.id) : [];
  const visibleEvents = run?.events.filter((event) => event.type !== "block.delta").slice(-20).reverse() ?? [];
  return <aside className={`activity-panel${open ? " activity-panel--open" : ""}`} aria-hidden={!open} aria-label="会话活动">
    <header><div><p>会话活动</p><span>运行状态、工具与用量</span></div><button className="icon-button" type="button" aria-label="关闭活动面板" onClick={onClose}><X size={17} /></button></header>
    <div className="activity-panel__body">
      <section className="activity-summary"><div className="activity-summary__icon"><Radio size={17} /></div><div><strong>{run?.run ? runStatusLabel(run.run.status) : "当前没有运行"}</strong><span>{run ? { idle: "等待新消息", connecting: "正在连接实时通道", live: "实时事件已连接", replaying: "正在回放事件", polling: "轮询恢复中" }[run.connectionState] : "选择对话后显示活动"}</span></div></section>
      {usage && <section className="activity-metrics"><div><span>输入</span><strong>{String(usage.input_tokens ?? usage.prompt_tokens ?? "—")}</strong></div><div><span>输出</span><strong>{String(usage.output_tokens ?? usage.completion_tokens ?? "—")}</strong></div><div><span>总计</span><strong>{String(usage.total_tokens ?? "—")}</strong></div></section>}
      {CHAT_TOOL_UI_ENABLED && (
        <section className="activity-timeline activity-timeline--tools">
          <h2><Wrench size={11} /> 工具活动</h2>
          {toolActivities.length ? toolActivities.map((activity) => <ToolActivityRow activity={activity} key={activity.tool_call_id} />) : <div className="activity-empty activity-empty--compact"><Database size={17} /><p>本轮暂无服务端工具调用。开启工具后，AI 读取健康档案的每一步都会在这里显示。</p></div>}
        </section>
      )}
      <section className="activity-timeline"><h2>时间线</h2>{visibleEvents.length ? visibleEvents.map((event) => <div className="activity-event" key={event.event_id}><span className="activity-event__dot">{event.type === "run.done" ? <CircleCheck size={13} /> : <Clock3 size={13} />}</span><div><strong>{EVENT_LABELS[event.type] ?? "运行事件"}</strong><time>{new Date(event.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time></div></div>) : <div className="activity-empty"><Activity size={19} /><p>发送消息后，这里会显示公开的运行状态和工具活动。</p></div>}</section>
    </div>
  </aside>;
}
