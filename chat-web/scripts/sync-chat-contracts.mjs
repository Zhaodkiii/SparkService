import { cp, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { dirname, join, resolve } from "node:path";

const projectRoot = resolve(import.meta.dirname, "../..");
const source = join(projectRoot, "chat_sync", "tests", "contracts");
const target = join(import.meta.dirname, "..", "contracts", "spark-chat-v1");

async function copyTree(from, to) {
  await mkdir(to, { recursive: true });
  for (const entry of await readdir(from, { withFileTypes: true })) {
    const sourcePath = join(from, entry.name);
    const targetPath = join(to, entry.name);
    if (entry.isDirectory()) await copyTree(sourcePath, targetPath);
    else await cp(sourcePath, targetPath);
  }
}

await mkdir(dirname(target), { recursive: true });
await copyTree(source, target);
const manifest = JSON.parse(await readFile(join(target, "manifest.json"), "utf8"));
manifest.spark_web_snapshot = { source: "chat_sync/tests/contracts", synced_at: new Date().toISOString() };
for (const item of manifest.files ?? []) {
  const digest = createHash("sha256").update(await readFile(join(target, item.path))).digest("hex");
  item.sha256 = digest;
}
await writeFile(join(target, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`Synced Spark chat contracts to ${target}`);
