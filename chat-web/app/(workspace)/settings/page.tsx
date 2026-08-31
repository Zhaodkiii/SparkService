"use client";

import { Settings } from "lucide-react";

export default function SettingsPage() {
  return (
    <section className="knowledge-page">
      <header className="knowledge-page__header">
        <div>
          <p className="feature-page__eyebrow">SETTINGS</p>
          <h1>设置</h1>
          <p>账户、通知与模型偏好将在后续阶段接入。</p>
        </div>
      </header>
      <div className="knowledge-overview">
        <article>
          <h2><Settings size={16} /> 其他</h2>
          <p>账户、通知与模型偏好将在后续阶段接入。</p>
        </article>
      </div>
    </section>
  );
}
