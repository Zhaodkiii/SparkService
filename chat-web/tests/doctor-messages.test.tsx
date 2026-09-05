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

  it("renders patient imageGallery blocks as images instead of dropping them", () => {
    const galleryMessage = message({
      client_message_id: "p2",
      role: "user",
      actor_type: "patient",
      blocks: [
        {
          id: "p2-gallery",
          kind: "imageGallery",
          status: "ready",
          revision: 1,
          order_key: 1,
          node_role: "timeline",
          // iOS 线上形态：_0 直接是图片数组
          payload: { image_gallery: { _0: [{ url: "https://oss.example/ct.webp", type: "image", file_id: 2568 }] } },
        },
        textBlock("p2-text", "看看这个"),
      ],
    });
    const { container } = render(<DoctorMessageList patientName="演示患者 03" messages={[galleryMessage]} />);

    expect(container.querySelector(".block--gallery")).not.toBeNull();
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(screen.getByText("看看这个")).toBeInTheDocument();
  });
});

describe("consult variant messages (DOCTOR-WORKSPACE-000004 页面形态修订)", () => {
  it("renders patient left bubble with avatar, attachment label and doctor right bubble with title", () => {
    const galleryMessage = message({
      client_message_id: "c-p1",
      role: "user",
      actor_type: "patient",
      blocks: [
        textBlock("c-p1-text", "医生您好，最近胸口闷"),
        {
          id: "c-p1-gallery",
          kind: "imageGallery",
          status: "ready",
          revision: 1,
          order_key: 2,
          node_role: "timeline",
          payload: {
            image_gallery: {
              _0: [
                { url: "https://oss.example/a.jpg", type: "image", file_id: 1 },
                { url: "https://oss.example/b.jpg", type: "image", file_id: 2 },
              ],
            },
          },
        },
      ],
    });
    const doctorMessage = message(
      {
        client_message_id: "c-d1",
        role: "assistant",
        actor_type: "doctor",
        sender: {
          display_name: "张医生 · 真人医生",
          doctor: { doctor_id: "doc", display_name: "张医生", title: "主任医师", hospital_name: "测试医院", department_name: "心内科", avatar_url: "", verified: true },
        },
      },
      "建议先完善心电图检查",
    );
    render(<DoctorMessageList variant="consult" patientName="吧宝贝" messages={[galleryMessage, doctorMessage]} />);

    // 患者：左侧气泡 + “患者 时间” + 附件（2）
    expect(screen.getByText("医生您好，最近胸口闷")).toBeInTheDocument();
    expect(screen.getByText("附件（2）")).toBeInTheDocument();
    expect(screen.getByText("医生您好，最近胸口闷").closest("[data-actor]")).toHaveAttribute("data-actor", "patient");
    // 医生：右侧气泡 + “姓名 · 职称 · 科室 时间”
    expect(screen.getByText(/张医生 · 主任医师 · 心内科/)).toBeInTheDocument();
    expect(screen.getByText("建议先完善心电图检查").closest("[data-actor]")).toHaveAttribute("data-actor", "doctor");
  });

  it("renders system text as centered tip and skips system cards without text", () => {
    render(<DoctorMessageList
      variant="consult"
      messages={[
        message({ client_message_id: "c-s1", role: "system", actor_type: "system" }, "请在充分了解病情后进行专业回复"),
        message({
          client_message_id: "c-s2",
          role: "system",
          actor_type: "system",
          blocks: [
            {
              id: "c-s2-card",
              kind: "hospitalDoctorIntroCard" as never,
              status: "ready",
              revision: 1,
              order_key: 1,
              node_role: "timeline",
              payload: { hospital_doctor_intro_card: { _0: {} } },
            },
          ],
        }),
      ]}
    />);
    expect(screen.getByText(/系统提示：请在充分了解病情后进行专业回复/)).toBeInTheDocument();
    expect(screen.queryByText("系统事件")).not.toBeInTheDocument();
  });

  it("default variant keeps original layout without consult bubbles", () => {
    const { container } = render(<DoctorMessageList messages={[message({ client_message_id: "n1", role: "user", actor_type: "patient" }, "有出汗")]} />);
    expect(container.querySelector(".consult-msg")).toBeNull();
    expect(screen.getByText(/患者 · /)).toBeInTheDocument();
  });
});
