"use client";

import { Activity, BookOpen, HeartPulse, MessageCircle, Settings, Sparkles, Utensils } from "lucide-react";

const items = [
  ["对话", MessageCircle], ["知识库", BookOpen], ["医疗", HeartPulse], ["饮食", Utensils], ["运动", Activity], ["记忆", Sparkles],
] as const;

export function GlobalNavigationRail() {
  return <nav className="global-rail" aria-label="全局导航">
    <div className="global-rail__logo" aria-label="小鲸健康 AI">鲸</div>
    {items.map(([label, Icon], index) => <button className={`nav-item ${index === 0 ? "nav-item--active" : ""}`} key={label} aria-current={index === 0 ? "page" : undefined}><Icon size={20} aria-hidden="true" /><span>{label}</span></button>)}
    <button className="nav-item nav-item--bottom" aria-label="设置"><Settings size={20} aria-hidden="true" /><span>设置</span></button>
  </nav>;
}
