import { notFound } from "next/navigation";
import { ChatRuntimeProvider, type FixtureScenario } from "@/context/ChatRuntimeContext";
import { ChatWorkspace } from "@/components/chat/home/ChatWorkspace";

const scenarios: FixtureScenario[] = ["empty", "history", "streaming", "gap", "unknown", "offline", "forbidden"];

export default function FixtureGalleryPage() {
  if (process.env.NODE_ENV === "production" || process.env.CHAT_WEB_ENABLE_FIXTURES !== "1") notFound();
  return <main className="fixture-gallery"><h1>P0 状态画廊</h1>{scenarios.map((scenario) => <section className="fixture-card" key={scenario}><div className="fixture-card__label">{scenario}</div><ChatRuntimeProvider initialScenario={scenario}><ChatWorkspace /></ChatRuntimeProvider></section>)}</main>;
}
