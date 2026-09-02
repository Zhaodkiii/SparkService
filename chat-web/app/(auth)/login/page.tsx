"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Apple, ArrowRight, Phone, ShieldCheck } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { appleWebErrorForCode } from "@/lib/auth/apple-web-errors";
import { safeReturnPath } from "@/lib/auth/return-path";

function pageReturnTo() {
  return typeof window === "undefined" ? "/chat" : safeReturnPath(new URLSearchParams(window.location.search).get("return_to"));
}

export default function LoginPage() {
  const [consented, setConsented] = useState(false);
  const router = useRouter(); const auth = useAuth(); const [error, setError] = useState<string | null>(null); const [appleBusy, setAppleBusy] = useState(false);
  const returnTo = pageReturnTo();
  useEffect(() => { if (auth.status === "authenticated") router.replace(pageReturnTo() as never); }, [auth.status, router]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("error");
    if (code) setError(appleWebErrorForCode(code));
  }, []);
  const apple = async () => { setAppleBusy(true); setError(null); try { const response = await fetch(`/api/auth/apple/start?return_to=${encodeURIComponent(returnTo)}`, { cache: "no-store" }); const body = await response.json(); if (!response.ok || !body.data?.authorization_url) throw new Error(body.msg || "Apple 登录暂不可用"); window.location.assign(body.data.authorization_url); } catch (cause) { setError(cause instanceof Error ? cause.message : "Apple 登录暂不可用"); setAppleBusy(false); } };
  return <main className="login-page"><section className="login-card login-card--wide" role="dialog" aria-modal="true" aria-labelledby="login-title"><div className="login-visual" aria-hidden="true"><div className="login-orbit"><ShieldCheck size={28} /></div><span>小鲸健康 AI</span><small>你的健康对话，安全同步</small></div><div className="login-panel"><h1 id="login-title">登录以解锁更多功能</h1><p className="login-subtitle">登录后，Web 与客户端共享同一套对话</p><div className="login-actions"><button className="login-option" disabled={!consented} onClick={() => router.push((returnTo === "/chat" ? "/login/phone" : `/login/phone?return_to=${encodeURIComponent(returnTo)}`) as never)}><Phone size={19} aria-hidden="true" />手机号登录<ArrowRight size={16} aria-hidden="true" /></button><button className="login-option login-option--apple" disabled={!consented || appleBusy} onClick={() => void apple()}><Apple size={19} aria-hidden="true" />{appleBusy ? "正在跳转…" : "使用 Apple 登录"}</button></div><label className="consent"><input type="checkbox" checked={consented} onChange={(event) => setConsented(event.target.checked)} /> <span>已阅读并同意 <a href="/legal/terms">用户协议</a> 和 <a href="/legal/privacy">隐私政策</a></span></label>{error && <p role="alert" className="login-error">{error}</p>}</div></section></main>;
}
