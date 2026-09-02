import { describe, expect, it } from "vitest";
import { hospitalApiPathFromRequest, sparkApiPathFromRequest } from "@/lib/server/upstream";

describe("hospital API BFF path forwarding", () => {
  it("preserves the hospital prefix, trailing slash and query string", () => {
    const request = new Request("http://localhost:9001/api/hospital/v1/doctor/conversations/?queue=pending&keyword=chest");
    expect(hospitalApiPathFromRequest(request)).toBe("/api/hospital/v1/doctor/conversations/?queue=pending&keyword=chest");
  });

  it("rejects paths outside the hospital API proxy namespace", () => {
    expect(() => hospitalApiPathFromRequest(new Request("http://localhost:9001/api/v1/ai/chat/sync/thread-pull/"))).toThrow(
      "Unsupported hospital API proxy path",
    );
  });

  it("keeps the patient Spark proxy from accepting hospital paths", () => {
    expect(() => sparkApiPathFromRequest(new Request("http://localhost:9001/api/hospital/v1/me/"))).toThrow(
      "Unsupported Spark API proxy path",
    );
  });
});
