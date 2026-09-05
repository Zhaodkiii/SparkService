/** DOCTOR-WORKSPACE-000004 第 12 问：常用语/快捷回复。
 *
 * 首期只作为医生输入辅助：点击后填充输入框，由医生确认后手动发送，
 * 不自动代替医生发送，不改变医生责任归属。
 */

export interface QuickReply {
  id: string;
  title: string;
  content: string;
}

export const DEFAULT_QUICK_REPLIES: QuickReply[] = [
  { id: "greeting", title: "接诊问候", content: "您好，我是您的主治医生，已经看到您的问诊信息，请详细描述一下您目前最主要的不适。" },
  { id: "ask_duration", title: "询问病程", content: "请问这种症状持续多长时间了？之前是否出现过类似情况？" },
  { id: "ask_history", title: "询问病史", content: "请问您是否有相关既往病史、过敏史，或正在长期服用其他药物？" },
  { id: "ask_report", title: "补充检查资料", content: "方便的话，请把近期的检查报告或化验单拍照上传，我会结合资料给您建议。" },
  { id: "advice_rest", title: "休息观察", content: "目前建议先注意休息、清淡饮食，密切观察症状变化，如有加重请及时告诉我。" },
  { id: "offline", title: "建议线下就诊", content: "根据您描述的情况，建议尽快到线下医疗机构面诊，必要时完善相关检查。" },
  { id: "closing", title: "结束叮嘱", content: "本次问诊的建议供您参考，不构成最终诊断。如症状持续或加重，请及时复诊或发起新的问诊。" },
];
