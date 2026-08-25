import { redirect } from "next/navigation";

export default async function LegacyChatPage({ params }: { params: Promise<{ threadId?: string[] }> }) {
  const { threadId } = await params;
  redirect((threadId?.length ? `/home/${threadId.map(encodeURIComponent).join("/")}` : "/home") as never);
}
