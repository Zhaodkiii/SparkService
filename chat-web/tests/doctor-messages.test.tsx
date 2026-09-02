import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DoctorMessageList } from "@/components/doctor/DoctorMessages";
import type { DoctorMessageDTO } from "@/types/hospital";

function textBlock(id: string, text: string) {
  return { id, kind: "text" as const, status: "ready" as const, revision: 1, order_key: 1, node_role: "timeline", payload: { text: { _0: text } } };
}

function message(partial: Partial<DoctorMessageDTO> & Pick<DoctorMessageDTO, "client_message_id" | "actor_type" | "role">, text = "正文"): DoctorMessageDTO {
  return {
    thread_id: "thread-1",
    delivery_state: "sent",
    created_at: "2026-09-01T10:32:00.000Z",
    blocks: partial.blocks ?? [textBlock(`${partial.client_message_id}-text`, text)],
    ...partial,
  };
}

describe("doctor message attribution", () => {
  it("renders patient, AI, doctor and system as distinct identities", () => {
    render(<DoctorMessageList
      patientName="演示患者 03"
      messages={[
        message({ client_message_id: "p1", role: "user", actor_type: "patient" }, "有出汗"),
        message({ client_message_id: "a1", role: "assistant", actor_type: "ai_agent", sender: { display_name: "张医生 AI 助手", agent: { agent_id: "ag", display_name: "张医生 AI 助手", is_ai: true } } }, "需要进一步确认"),
        message({ client_message_id: "d1", role: "assistant", actor_type: "doctor", sender: { doctor: { doctor_id: "doc", display_name: "张医生", title: "主任医师", hospital_name: "天长市中医院", department_name: "心内科", avatar_url: "", verified: true } } }, "请立即停止活动"),
        message({ client_message_id: "s1", role: "system", actor_type: "system" }, "张医生已接管本次会话"),
      ]}
    />);

    expect(screen.getByText(/患者 · 演示患者 03/)).toBeInTheDocument();
    expect(screen.getByText("有出汗")).toBeInTheDocument();
    expect(screen.getByText("AI")).toBeInTheDocument();
    expect(screen.getByText(/张医生 AI 助手/)).toBeInTheDocument();
    expect(screen.getByText("真人医生")).toBeInTheDocument();
    expect(screen.getByText(/张医生 · 主任医师/)).toBeInTheDocument();
    expect(screen.getByText(/张医生已接管本次会话/)).toBeInTheDocument();
    expect(screen.getByText("有出汗").closest("[data-actor]")).toHaveAttribute("data-actor", "patient");
    expect(screen.getByText("需要进一步确认").closest("[data-actor]")).toHaveAttribute("data-actor", "ai_agent");
    expect(screen.getByText("请立即停止活动").closest("[data-actor]")).toHaveAttribute("data-actor", "doctor");
    expect(screen.getByText(/张医生已接管本次会话/).closest("[data-actor]")).toHaveAttribute("data-actor", "system");
  });

  it("does not treat assistant role as AI when actor_type is doctor", () => {
    render(<DoctorMessageList messages={[message({ client_message_id: "d2", role: "assistant", actor_type: "doctor", sender: { doctor: { doctor_id: "doc", display_name: "李医生", title: "主治医师", hospital_name: "", department_name: "", avatar_url: "", verified: true } } })]} />);
    expect(screen.getByText("真人医生")).toBeInTheDocument();
    expect(screen.queryByText("AI")).not.toBeInTheDocument();
  });
});
