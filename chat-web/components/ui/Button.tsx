"use client";

import type { ButtonHTMLAttributes } from "react";

export function Button({ variant = "default", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "ghost" }) {
  const className = ["action-button", variant === "primary" ? "send-button" : "", props.className ?? ""].filter(Boolean).join(" ");
  return <button {...props} className={className} />;
}
