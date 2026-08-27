import { createHash } from "node:crypto";

/** Keep the raw value in the server-side transaction and send only its digest to Apple. */
export function appleNonceDigest(rawNonce: string): string {
  return createHash("sha256").update(rawNonce, "utf8").digest("hex");
}
