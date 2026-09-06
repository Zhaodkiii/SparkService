import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";
import { AttachmentPreviewProvider } from "@/components/shared/AttachmentPreviewProvider";

export const metadata: Metadata = {
  title: "小鲸健康 AI",
  description: "SparkService AI 对话工作区",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthProvider>
          <AttachmentPreviewProvider>{children}</AttachmentPreviewProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
