import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { zipSync, strToU8 } from "fflate";
import {
  newEditor,
  reviewFor,
  selectedPhotos,
  selectedContent,
  SessionGate,
  reviewProblem,
  productionDirty,
  notificationText,
  canonical,
} from "../src/features/customizations/domain";
import { inspectArchive } from "../src/features/customizations/archive";
import type {
  Detail,
  Delivery,
  Notice,
} from "../src/features/customizations/types";
function detail(id = "A"): Detail {
  return {
    id,
    number: "C20261020-00000000",
    title: "当前内容",
    brief: { description: "当前故事" },
    status: "in_production",
    revision: 1,
    owner_id: 1,
    owner_name: "测试用户",
    assigned_to: 2,
    assigned_name: "测试管理员",
    updated_at: "2026-10-20T00:00:00Z",
    due_at: null,
    pending_submission: false,
    cancellation_requested: false,
    overdue: false,
    assets: [],
    submissions: [
      {
        id: 1,
        number: 1,
        created_at: "2026-10-20T00:00:00Z",
        snapshot: {
          title: "最初提交",
          brief: { description: "旧故事" },
          assets: [
            {
              id: "photo-1",
              position: 0,
              note: "旧备注",
              must_use: true,
              crop_allowed: false,
            },
          ],
        },
        resolved_assets: [
          {
            id: "photo-1",
            position: 0,
            note: "旧备注",
            must_use: true,
            crop_allowed: false,
          },
        ],
      },
      {
        id: 2,
        number: 2,
        created_at: "2026-10-20T01:00:00Z",
        snapshot: {
          title: "补充提交",
          brief: { description: "新故事" },
          assets: [],
        },
        resolved_assets: [],
      },
    ],
    accepted_submission_id: 1,
    latest_submission_id: 2,
    current_delivery_id: null,
    internal_note: "服务器备注",
    allowed_actions: ["deliver"],
    next_step: "制作中",
    reminder_available_at: null,
    deliveries: [],
    jobs: [],
    events: [],
    notifications: [],
    audit: [],
  };
}
const candidate = {
  id: "candidate-1",
  status: "ready_for_review",
  submission_id: 1,
} as Delivery;
test("switching requests creates a clean editor, with no prior reviews or input", () => {
  const a = newEditor(detail());
  a.internalNote = "A的修改";
  reviewFor(a, candidate.id).reviewed = true;
  reviewFor(a, candidate.id).message = "A的交付说明";
  const b = newEditor(detail("B"));
  assert.equal(b.internalNote, "服务器备注");
  assert.deepEqual(b.reviews, {});
  assert.equal(b.submission, 2);
});
test("selected snapshot changes title, brief, photos and their original notes together", () => {
  const d = detail(),
    e = newEditor(d);
  e.submission = 1;
  assert.equal(selectedContent(d, e).title, "最初提交");
  assert.equal(selectedPhotos(d, e)[0]?.note, "旧备注");
  e.submission = 2;
  assert.equal(selectedContent(d, e).brief.description, "新故事");
  assert.deepEqual(selectedPhotos(d, e), []);
});
test("candidate approval and used-photo selection never leak into another candidate", () => {
  const d = detail(),
    e = newEditor(d);
  const a = reviewFor(e, "candidate-1");
  a.reviewed = true;
  a.used = ["photo-1"];
  assert.equal(reviewProblem(d, candidate, e), "");
  const b = { ...candidate, id: "candidate-2" };
  assert.match(reviewProblem(d, b, e), /先完成/);
  assert.deepEqual(reviewFor(e, "candidate-2").used, []);
});
test("review rejects missing required photos and candidates from an old production basis", () => {
  const d = detail(),
    e = newEditor(d);
  reviewFor(e, candidate.id).reviewed = true;
  assert.match(reviewProblem(d, candidate, e), /必用照片/);
  d.accepted_submission_id = 2;
  assert.match(reviewProblem(d, candidate, e), /过期/);
});
test("late responses after switching or closing a request cannot belong to the new session", () => {
  const gate = new SessionGate(),
    a = gate.change(),
    b = gate.change();
  assert.equal(gate.current(a), false);
  assert.equal(gate.current(b), true);
  gate.change();
  assert.equal(gate.current(b), false);
});
test("unsaved production edits remain detectable for conflict and leave protection", () => {
  const d = detail(),
    e = newEditor(d);
  assert.equal(productionDirty(e, d), false);
  e.internalNote = "本地未保存";
  assert.equal(productionDirty(e, d), true);
});
test("idempotency payload has stable ordering and changes when scope or content changes", () => {
  assert.equal(
    canonical({ revision: 2, message: "原因" }),
    canonical({ message: "原因", revision: 2 }),
  );
  assert.notEqual(
    canonical({ id: "A", revision: 2 }),
    canonical({ id: "B", revision: 2 }),
  );
});
test("notification distinguishes read, APNs acceptance and topic opt-out", () => {
  const n = {
    seen: false,
    status: "completed",
    deliveries: [{ status: "accepted" }],
    outbox: [],
  } as unknown as Notice;
  assert.match(notificationText(n), /尚未知/);
  n.seen = true;
  assert.match(notificationText(n), /已查看/);
  n.seen = false;
  n.deliveries = [];
  n.outbox = [{ last_error: "topic_opt_out" }] as Notice["outbox"];
  assert.match(notificationText(n), /关闭/);
});
function archive(requestID: string) {
  return new Blob([
    zipSync(
      {
        "package.json": strToU8(
          JSON.stringify({
            audience: "private",
            customizationRequestID: requestID,
            templateBookID: "custom-" + requestID,
            packageVersion: 3,
            title: "私人包",
            pages: [{ id: "p" }],
          }),
        ),
        "large.bin": new Uint8Array(5 * 1024 ** 2).fill(17),
      },
      { level: 0 },
    ),
  ]);
}
test("archive preflight reads manifest and hashes multiple chunks with the correct SHA-256", async () => {
  const file = archive("A"),
    progress: number[] = [];
  const r = await inspectArchive(file, "A", (n) => progress.push(n));
  assert.equal(r.packageVersion, 3);
  assert.equal(r.pageCount, 1);
  assert.equal(
    r.sha,
    createHash("sha256")
      .update(Buffer.from(await file.arrayBuffer()))
      .digest("hex"),
  );
  assert.ok(progress.length > 1);
  assert.equal(progress.at(-1), 1);
});
test("archive belonging to another request is rejected before upload or hashing", async () => {
  await assert.rejects(
    () =>
      inspectArchive(archive("A"), "B", () =>
        assert.fail("must reject before hashing"),
      ),
    /包内需求：A；当前需求：B/,
  );
});
test("public source reports the missing private marker rather than an ambiguous mismatch", async () => {
  const file = new Blob([
    zipSync({
      "package.json": strToU8(
        JSON.stringify({ templateBookID: "public-book", packageVersion: 1 }),
      ),
    }),
  ]);
  await assert.rejects(
    () => inspectArchive(file, "A", () => {}),
    /没有专属定制标记/,
  );
});
test("invalid ZIP is rejected without allocating the entire file", async () => {
  await assert.rejects(
    () => inspectArchive(new Blob(["not a zip"]), "A", () => {}),
    /ZIP/,
  );
});
test("compressed package.json is inspected correctly", async () => {
  const file = new Blob([
    zipSync({
      "package.json": strToU8(
        JSON.stringify({
          audience: "private",
          customizationRequestID: "A",
          templateBookID: "custom-A",
          packageVersion: 1,
          pages: [],
        }),
      ),
    }),
  ]);
  assert.equal((await inspectArchive(file, "A", () => {})).packageVersion, 1);
});
