"use client";

import { Activity, CircleCheck, Clock3, Radio, X } from "lucide-react";
import { useOptionalRunControl } from "@/context/RunControlContext";
import { runStatusLabel } from "@/lib/event-reducer";

const EVENT_LABELS: Record<string, string> = { "run.queued": "请求已进入队列", "run.started": "开始生成回答", "assistant.status": "生成状态更新", "block.created": "创建回答内容", "block.delta": "接收流式内容", "block.completed": "回答内容完成", "usage.final": "用量统计完成", "run.done": "本轮对话结束" };

export function SessionActivityPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const run = useOptionalRunControl();
  const usage = run?.run ? run.state.usageByRun[run.run.id] : null;
  const visibleEvents = run?.events.filter((event) => event.type !== "block.delta").slice(-20).reverse() ?? [];
  return <aside className={`activity-panel${open ? " activity-panel--open" : ""}`} aria-hidden={!open} aria-label="会话活动">
    <header><div><p>会话活动</p><span>运行状态、事件与用量</span></div><button className="icon-button" type="button" aria-label="关闭活动面板" onClick={onClose}><X size={17} /></button></header>
    <div className="activity-panel__body">
      <section className="activity-summary"><div className="activity-summary__icon"><Radio size={17} /></div><div><strong>{run?.run ? runStatusLabel(run.run.status) : "当前没有运行"}</strong><span>{run ? { idle: "等待新消息", connecting: "正在连接实时通道", live: "实时事件已连接", replaying: "正在回放事件", polling: "轮询恢复中" }[run.connectionState] : "选择对话后显示活动"}</span></div></section>
      {usage && <section className="activity-metrics"><div><span>输入</span><strong>{String(usage.input_tokens ?? usage.prompt_tokens ?? "—")}</strong></div><div><span>输出</span><strong>{String(usage.output_tokens ?? usage.completion_tokens ?? "—")}</strong></div><div><span>总计</span><strong>{String(usage.total_tokens ?? "—")}</strong></div></section>}
      <section className="activity-timeline"><h2>时间线</h2>{visibleEvents.length ? visibleEvents.map((event) => <div className="activity-event" key={event.event_id}><span className="activity-event__dot">{event.type === "run.done" ? <CircleCheck size={13} /> : <Clock3 size={13} />}</span><div><strong>{EVENT_LABELS[event.type] ?? "运行事件"}</strong><time>{new Date(event.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time></div></div>) : <div className="activity-empty"><Activity size={19} /><p>发送消息后，这里会显示公开的运行状态和工具活动。</p></div>}</section>
    </div>
  </aside>;
}
