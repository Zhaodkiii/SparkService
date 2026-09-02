import { blockAssociatedValue } from "@/lib/chat/block-normalizer";
import { actorPrefix } from "@/lib/hospital/labels";
import type { DoctorMessageDTO, HospitalActorType } from "@/types/hospital";

export function doctorMessagePlainText(message: Pick<DoctorMessageDTO, "blocks">): string {
  return message.blocks.map((block) => {
    const value = blockAssociatedValue(block);
    return typeof value === "string" ? value : "";
  }).filter(Boolean).join("\n\n");
}

export function conversationPreview(title: string, lastMessage?: DoctorMessageDTO | null): string {
  if (!lastMessage) return title;
  const text = doctorMessagePlainText(lastMessage).replace(/\s+/g, " ").trim();
  if (!text) return title;
  return `${actorPrefix(lastMessage.actor_type as HospitalActorType | null, lastMessage.sender?.doctor?.display_name || lastMessage.sender?.display_name)}${text}`;
}

export function inferActorType(message: DoctorMessageDTO): HospitalActorType {
  if (message.actor_type) return message.actor_type;
  if (message.sender?.actor_type) return message.sender.actor_type;
  if (message.role === "user") return "patient";
  if (message.role === "system") return "system";
  return "ai_agent";
}

export function firstRiskMessageId(messages: DoctorMessageDTO[]): string | null {
  for (const message of messages) {
    if (message.blocks.some((block) => block.kind === "medicalRiskNotice")) {
      return message.client_message_id;
    }
  }
  return null;
}
