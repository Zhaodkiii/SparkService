import { describe, expect, it } from "vitest";
import { appleNonceDigest } from "@/lib/server/apple-nonce";

describe("Apple Web nonce contract", () => {
  it("sends a stable SHA-256 hex digest for the raw cookie nonce", () => {
    const rawNonce = "39334063-7147-440c-89a8-f883bdb745c7";
    expect(appleNonceDigest(rawNonce)).toBe(
      "46d89de53527abccf7d4240db867f0989d749f0bd3b78b2d8a9069f08fff6ed5",
    );
    expect(appleNonceDigest(rawNonce)).not.toBe(rawNonce);
    expect(appleNonceDigest(rawNonce)).toMatch(/^[0-9a-f]{64}$/);
  });
});
