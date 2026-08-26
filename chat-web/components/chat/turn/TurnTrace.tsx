"use client";

import { CheckCircle2, CircleAlert, Loader2, Sparkles } from "lucide-react";
import type { AgentRoundTraceDTO, TurnTraceNode } from "@/types/chat";
import { TurnTraceRow } from "@/components/chat/turn/TurnTraceRow";

function roundLabel(round: AgentRoundTraceDTO): string {
  if (round.status === "failed") return "本轮调用失败";
  if (round.status === "running") return "正在思考";
  if (round.call_role === "narration") return "已规划后续工具调用";
  return "已完成回答";
}

function RoundIcon({ round }: { round: AgentRoundTraceDTO }) {
  if (round.status === "running") return <Loader2 size={12} className="turn-trace__spin" aria-hidden="true" />;
  if (round.status === "failed") return <CircleAlert size={12} aria-hidden="true" />;
  return <CheckCircle2 size={12} aria-hidden="true" />;
}

/** 单条 Agent Round 轨迹：只展示公开阶段与公开摘要，不渲染隐藏 reasoning。 */
function TurnTraceRoundRow({ round }: { round: AgentRoundTraceDTO }) {
  const summary = round.public_summary.trim() ? round.public_summary.trim() : roundLabel(round);
  return <li className={`turn-trace turn-trace--round turn-trace--${round.status === "failed" ? "error" : "active"}`}>
    <span className="turn-trace__icon"><RoundIcon round={round} /></span>
    <strong><Sparkles size={11} className="turn-trace__round-mark" aria-hidden="true" />模型</strong>
    <span className="turn-trace__summary">{summary}</span>
  </li>;
}

/** 回合轨迹（能力三）：按轮次合并 Round 与工具调用，顺序稳定可回放。 */
export function TurnTrace({ nodes }: { nodes: TurnTraceNode[] }) {
  if (!nodes.length) return null;
  return <ul className="turn-trace-list">
    {nodes.map((node) => (node.kind === "round"
      ? <TurnTraceRoundRow round={node.round} key={node.round.round_id} />
      : <TurnTraceRow activity={node.tool} key={node.tool.tool_call_id} />))}
  </ul>;
}