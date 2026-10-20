import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import Antd, { Select } from "ant-design-vue";
import Workspace from "../src/views/CustomizationRequestsView.vue";
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../src/api/http", () => ({
  default: mocks,
  ApiError: class ApiError extends Error {
    status?: number;
    constructor(m: string, s?: number) {
      super(m);
      this.status = s;
    }
  },
}));
vi.mock("../src/stores/auth", () => ({
  useAuthStore: () => ({ user: { id: 7 } }),
}));
const photo = (id: string, note: string) => ({
  id,
  position: 0,
  note,
  must_use: true,
  crop_allowed: true,
  status: "ready",
  available: true,
  width: 100,
  height: 100,
  size: 100,
});
function detail() {
  const a = photo("photo-a", "旧版照片备注"),
    b = photo("photo-b", "新版照片备注");
  return {
    id: "A",
    number: "C20261020-AAAAAAAA",
    title: "海边主题",
    owner_id: 1,
    owner_name: "测试用户",
    assigned_name: "测试设计师",
    assigned_to: 7,
    status: "in_production",
    revision: 3,
    due_at: null,
    updated_at: "2026-10-20T00:00:00Z",
    pending_submission: true,
    cancellation_requested: false,
    overdue: false,
    brief: { description: "当前故事" },
    assets: [b],
    submissions: [
      {
        id: 1,
        number: 1,
        created_at: "2026-10-19T00:00:00Z",
        snapshot: {
          title: "最初提交标题",
          brief: { description: "旧版故事内容" },
          assets: [a],
        },
        resolved_assets: [a],
      },
      {
        id: 2,
        number: 2,
        created_at: "2026-10-20T00:00:00Z",
        snapshot: {
          title: "补充提交标题",
          brief: { description: "新版故事内容" },
          assets: [b],
        },
        resolved_assets: [b],
      },
    ],
    accepted_submission_id: 1,
    latest_submission_id: 2,
    internal_note: "内部备注",
    allowed_actions: ["accept", "production", "assign", "cancel", "reject"],
    next_step: "请确认最新资料",
    reminder_available_at: null,
    deliveries: [],
    jobs: [],
    events: [],
    notifications: [],
    audit: [],
  };
}
let wrapper: VueWrapper;
beforeEach(() => {
  sessionStorage.clear();
  mocks.get.mockReset();
  mocks.post.mockReset();
  mocks.get.mockImplementation(async (path: string) =>
    path.includes("operators")
      ? { results: [{ id: 7, name: "设计师" }] }
      : path.includes("requests/?")
        ? { results: [detail()], next_page: null, summary: { pending_info: 1 } }
        : detail(),
  );
});
afterEach(() => {
  wrapper?.unmount();
  document.body.innerHTML = "";
});
async function render() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/diary-customizations", component: Workspace }],
  });
  await router.push("/diary-customizations");
  await router.isReady();
  wrapper = mount(
    { template: "<router-view />" },
    { attachTo: document.body, global: { plugins: [router, Antd] } },
  );
  await flushPromises();
  const open = wrapper.findAll("button").find((b) => b.text() === "进入工作台");
  expect(open).toBeDefined();
  await open!.trigger("click");
  await flushPromises();
}
describe("rendered admin workspace", () => {
  it("shows Chinese fields and changes title, story and photo requirements with the selected snapshot", async () => {
    await render();
    expect(document.body.textContent).toContain("新版故事内容");
    expect(document.body.textContent).toContain("新版照片备注");
    expect(document.body.textContent).toContain("想记录的故事");
    const selector = wrapper
      .findAllComponents(Select)
      .find((c) => c.props("value") === 2);
    expect(selector).toBeDefined();
    selector!.vm.$emit("update:value", 1);
    await flushPromises();
    expect(document.body.textContent).toContain("旧版故事内容");
    expect(document.body.textContent).toContain("旧版照片备注");
    expect(document.body.textContent).not.toContain("新版故事内容");
  });
  it("does not fetch private image URLs just by opening the workspace", async () => {
    await render();
    expect(mocks.post).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain("点击加载预览");
  });
  it("image preview URLs are requested for the selected request and submission only", async () => {
    await render();
    mocks.post.mockResolvedValue({ assets: [] });
    const button = Array.from(document.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("加载 / 更新本组预览"),
    );
    expect(button).toBeDefined();
    button!.click();
    await flushPromises();
    expect(mocks.post.mock.calls[0]?.[0]).toContain("/requests/A/asset-urls/");
    expect(mocks.post.mock.calls[0]?.[1]).toEqual({
      asset_ids: ["photo-b"],
      submission_id: 2,
    });
  });
  it("keeps action errors visible inside the workbench", async () => {
    await render();
    const { ApiError } = await import("../src/api/http");
    mocks.post.mockRejectedValue(
      new ApiError("制作依据已变化，请重新核对", 409),
    );
    const accept = Array.from(document.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("确认新资料"),
    );
    expect(accept).toBeDefined();
    accept!.click();
    await flushPromises();
    await new Promise((r) => setTimeout(r, 20));
    await flushPromises();
    const dialog = document.querySelector(".ant-drawer-content");
    expect(dialog?.textContent).toContain("制作依据已变化");
  });
});
