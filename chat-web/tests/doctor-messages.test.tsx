import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DoctorMessageList } from "@/components/doctor/DoctorMessages";
import { AttachmentPreviewProvider } from "@/components/shared/AttachmentPreviewProvider";
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

  it("renders patient report references in the consult variant", () => {
    const reportMessage = message({
      client_message_id: "c-report",
      role: "user",
      actor_type: "patient",
      blocks: [{
        id: "c-report-reference",
        kind: "healthResourceReference" as never,
        status: "ready",
        revision: 1,
        order_key: 1,
        node_role: "timeline",
        payload: {
          health_resource_reference: {
            _0: { resource_type: "examination_report", resource_id: 327, member_id: 2, ref_index: 2 },
          },
        },
      }],
    });

    render(<DoctorMessageList variant="consult" patientName="吧宝贝" messages={[reportMessage]} />);

    expect(screen.getByRole("button", { name: "检查报告：检查报告 #327" })).toBeInTheDocument();
    expect(screen.getByText("资料编号：327 · 成员 2")).toBeInTheDocument();
  });
});

describe("consult variant messages (DOCTOR-WORKSPACE-000004 页面形态修订)", () => {
  it("renders the supplementary report request as a waiting card", () => {
    const reportRequest = message({
      client_message_id: "c-report-request",
      role: "assistant",
      actor_type: "doctor",
      blocks: [{
        id: "c-report-request-card",
        kind: "captureCard",
        status: "ready",
        revision: 1,
        order_key: 1,
        node_role: "toolPresentation",
        payload: {
          capture_card: {
            _0: { card_type: "supplementary_report", upload_mode: "composer", status: "pending" },
          },
        },
      }],
    });

    render(<DoctorMessageList variant="consult" messages={[reportRequest]} />);

    expect(screen.getByText("补充报告")).toBeInTheDocument();
    expect(screen.getByText("已向患者发送报告上传卡，等待患者补充。")).toBeInTheDocument();
  });

  it("shows uploaded reports inside the original supplementary report card", () => {
    const completedRequest = message({
      client_message_id: "c-report-completed",
      role: "assistant",
      actor_type: "doctor",
      blocks: [{
        id: "c-report-completed-card",
        kind: "captureCard",
        status: "ready",
        revision: 2,
        order_key: 1,
        node_role: "toolPresentation",
        payload: {
          capture_card: {
            _0: {
              card_type: "supplementary_report",
              status: "completed",
              selected_attachments: [
                { kind: "image", display_name: "检验单.jpg", public_url: "https://oss.example/report.jpg", mime_type: "image/jpeg", byte_count: 2048 },
                { kind: "pdf", display_name: "出院记录.pdf", public_url: "https://oss.example/report.pdf", mime_type: "application/pdf", byte_count: 4096 },
              ],
            },
          },
        },
      }],
    });

    render(<AttachmentPreviewProvider><DoctorMessageList variant="consult" messages={[completedRequest]} /></AttachmentPreviewProvider>);

    expect(screen.getByText("患者已补充报告，点击缩略图即可预览原文件。")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "检验单.jpg" })).toBeInTheDocument();
    expect(screen.getByText("出院记录.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /出院记录\.pdf/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("img", { name: "检验单.jpg" }).closest("button")!);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "检验单.jpg" })).toBeInTheDocument();
  });

  it("shows only one collapsible symptom summary and hides collection internals", () => {
    const summaryMessage = message({
      client_message_id: "c-symptom-summary",
      role: "assistant",
      actor_type: "ai_agent",
      blocks: [
        textBlock("c-symptom-advice", "根据症状建议立即前往急诊"),
        {
          id: "c-symptom-card",
          kind: "symptomCollectionCard" as never,
          status: "ready",
          revision: 1,
          order_key: 2,
          node_role: "toolPresentation",
          payload: {
            symptom_collection_card: {
              _0: {
                collection_id: "collection-doctor-1",
                task_status: "completed",
                snapshot: {
                  collection_id: "collection-doctor-1",
                  status: "completed",
                  analysis_summary: "主要不适为头晕，今天出现，伴恶心。",
                  primary_complaint: "头晕",
                },
              },
            },
          },
        },
      ],
    });
    const questionMessage = message({
      client_message_id: "c-symptom-question",
      role: "assistant",
      actor_type: "ai_agent",
      blocks: [{
        id: "c-symptom-question-card",
        kind: "toolQuestionCards" as never,
        status: "ready",
        revision: 1,
        order_key: 3,
        node_role: "toolPresentation",
        payload: {
          tool_question_cards: {
            _0: [{
              id: "round-doctor-1",
              status: "submitted",
              prompt: {
                symptom_collection_id: "collection-doctor-1",
                questions: [{ id: "q1", question: "这次头晕持续多久？", selection_mode: "single", options: [{ id: "today", text: "今天" }] }],
              },
              answers: [{ question_id: "q1", selected_option_ids: ["today"] }],
            }],
          },
        },
      }],
    });

    const { container } = render(<DoctorMessageList variant="consult" messages={[summaryMessage, questionMessage]} />);

    expect(container.querySelectorAll("[data-testid='symptom-collection-card']")).toHaveLength(1);
    expect(screen.getByText("症状信息汇总")).toBeInTheDocument();
    expect(screen.getByText(/问诊进度/)).toHaveTextContent("100%");
    expect(screen.getByText("主要不适为头晕，今天出现，伴恶心。")).toBeInTheDocument();
    expect(screen.queryByText(/建议立即前往急诊/)).not.toBeInTheDocument();
    expect(screen.queryByText(/这次头晕持续多久/)).not.toBeInTheDocument();
    expect(screen.queryByText(/问答记录/)).not.toBeInTheDocument();
  });

  it("renders pending symptom start card when doctor inserts collection without summary block", () => {
    const questionMessage = message({
      client_message_id: "c-symptom-start",
      role: "assistant",
      actor_type: "ai_agent",
      blocks: [{
        id: "c-symptom-start-card",
        kind: "toolQuestionCards" as never,
        status: "ready",
        revision: 1,
        order_key: 1,
        node_role: "toolPresentation",
        payload: {
          tool_question_cards: {
            _0: [{
              id: "round-start-1",
              status: "pending",
              prompt: {
                tool_name: "collect_symptoms",
                symptom_collection_id: "collection-start-1",
                questions: [{
                  id: "primary_complaint",
                  field_key: "primary_complaint",
                  question: "请描述您目前最主要的不适症状",
                  selection_mode: "single",
                  options: [],
                  allows_other: true,
                }],
              },
              answers: [],
            }],
          },
        },
      }],
    });

    render(<DoctorMessageList variant="consult" messages={[questionMessage]} />);

    expect(screen.getByText("症状采集")).toBeInTheDocument();
    expect(screen.getByText("请描述您目前最主要的不适症状")).toBeInTheDocument();
    expect(screen.getByText(/等待患者在 App 中填写/)).toBeInTheDocument();
    expect(screen.queryByText(/问诊进度/)).not.toBeInTheDocument();
  });

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

  it("renders consultationCard with inline image and file attachments", () => {
    const consultMessage = message({
      client_message_id: "c-card",
      role: "user",
      actor_type: "patient",
      blocks: [
        {
          id: "c-card-block",
          kind: "consultationCard" as never,
          status: "ready",
          revision: 1,
          order_key: 1,
          node_role: "timeline",
          payload: {
            consultation_card: {
              _0: {
                consult_no: "C202509060001",
                chief_complaint: "最近胸口闷",
                service_status: "pending_doctor",
                doctor: { display_name: "张医生", title: "主任医师" },
                department: { name: "心内科" },
                hospital: { name: "示例医院", short_name: "示例" },
                attachments: [
                  { id: "img-1", type: "image", url: "https://oss.example/chest.jpg", filename: "chest.jpg" },
                  { id: "pdf-1", type: "document", url: "https://oss.example/report.pdf", filename: "report.pdf", file_size: 2048 },
                ],
              },
            },
          },
        },
      ],
    });
    const { container } = render(<DoctorMessageList variant="consult" patientName="吧宝贝" messages={[consultMessage]} />);

    expect(screen.getByText("张医生")).toBeInTheDocument();
    expect(screen.getByText("主诉：最近胸口闷")).toBeInTheDocument();
    expect(screen.getByText("问诊编号：C202509060001")).toBeInTheDocument();
    expect(container.querySelector(".consult-card-block__gallery")).not.toBeNull();
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByRole("img")).toBeInTheDocument();
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
