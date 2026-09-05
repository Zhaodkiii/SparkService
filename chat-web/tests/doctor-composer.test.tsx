import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DoctorComposerView } from "@/components/doctor/DoctorComposer";

describe("doctor composer service states", () => {
  it("shows a join affordance while AI is serving", () => {
    render(<DoctorComposerView serviceStatus="ai_active" doctorLabel="张医生" onJoin={vi.fn()} />);
    expect(screen.getByRole("button", { name: "接管后可回复" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "医生回复" })).not.toBeInTheDocument();
  });

  it("shows join-and-reply when the conversation is pending", () => {
    const onJoin = vi.fn().mockResolvedValue(true);
    render(<DoctorComposerView serviceStatus="pending_doctor" doctorLabel="张医生" onJoin={onJoin} />);
    expect(screen.getByRole("button", { name: "接管问诊" })).toBeInTheDocument();
  });

  it("shows a read-only ended banner", async () => {
    render(<DoctorComposerView serviceStatus="ended" doctorLabel="张医生" />);
    expect(screen.getByText(/本次问诊已结束/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "医生回复" })).not.toBeInTheDocument();
  });

  it("keeps the draft when send fails", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn().mockResolvedValue(false);
    render(<DoctorComposerView serviceStatus="doctor_joined" doctorLabel="张医生" onSend={onSend} />);
    await user.type(screen.getByRole("textbox", { name: "医生回复" }), "请立即就医");
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(onSend).toHaveBeenCalledWith("请立即就医", [], []);
    expect(screen.getByRole("textbox", { name: "医生回复" })).toHaveValue("请立即就医");
  });

  it("clears the draft after a confirmed send", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn().mockResolvedValue(true);
    render(<DoctorComposerView serviceStatus="doctor_joined" doctorLabel="张医生" onSend={onSend} />);
    await user.type(screen.getByRole("textbox", { name: "医生回复" }), "请立即就医");
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(screen.getByRole("textbox", { name: "医生回复" })).toHaveValue("");
  });

  it("disables sending while realtime connection is down", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn().mockResolvedValue(true);
    render(<DoctorComposerView serviceStatus="doctor_joined" doctorLabel="张医生" onSend={onSend} connection="disconnected" />);
    await user.type(screen.getByRole("textbox", { name: "医生回复" }), "请立即就医");
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
    expect(screen.getByText(/实时连接已断开/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(onSend).not.toHaveBeenCalled();
  });

  it("fills the composer from a quick reply without auto-sending", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn().mockResolvedValue(true);
    render(
      <DoctorComposerView
        serviceStatus="doctor_joined"
        doctorLabel="张医生"
        onSend={onSend}
        quickReplies={[{ id: "q1", title: "接诊问候", content: "您好，请描述症状。" }]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "常用语" }));
    await user.click(screen.getByRole("menuitem", { name: /接诊问候/ }));
    expect(screen.getByRole("textbox", { name: "医生回复" })).toHaveValue("您好，请描述症状。");
    expect(onSend).not.toHaveBeenCalled();
  });
});
