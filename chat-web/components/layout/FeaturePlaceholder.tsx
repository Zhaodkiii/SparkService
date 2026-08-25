import type { LucideIcon } from "lucide-react";

export function FeaturePlaceholder({ icon: Icon, eyebrow, title, description }: { icon: LucideIcon; eyebrow: string; title: string; description: string }) {
  return <section className="feature-page"><div className="feature-page__content"><span className="feature-page__icon"><Icon size={22} /></span><p className="feature-page__eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p><div className="feature-page__status"><span />界面入口已对齐，业务数据将在对应阶段接入</div></div></section>;
}
