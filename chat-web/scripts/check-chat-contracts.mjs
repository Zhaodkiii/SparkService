import { readFile, readdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const source = join(root, "..", "chat_sync", "tests", "contracts");
const target = join(root, "contracts", "spark-chat-v1");

async function digest(path) { return createHash("sha256").update(await readFile(path)).digest("hex"); }
const sourceManifest = JSON.parse(await readFile(join(source, "manifest.json"), "utf8"));
const targetManifest = JSON.parse(await readFile(join(target, "manifest.json"), "utf8"));
const mismatches = [];
for (const item of sourceManifest.files ?? []) {
  const sourceHash = await digest(join(source, item.path));
  const targetHash = await digest(join(target, item.path));
  if (sourceHash !== targetHash) mismatches.push(`${item.path}: source ${sourceHash} target ${targetHash}`);
}
if (mismatches.length || sourceManifest.contract_manifest_version !== targetManifest.contract_manifest_version) {
  console.error("Chat contract snapshot drift detected:\n" + mismatches.join("\n"));
  process.exit(1);
}
console.log(`Chat contract snapshot is aligned (${sourceManifest.files?.length ?? 0} files).`);
