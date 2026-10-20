import { createSHA256 } from "hash-wasm";
import { inflateSync } from "fflate";
import type { ArchiveInfo } from "./types";
export async function inspectArchive(
  file: Blob,
  requestID: string,
  progress: (n: number) => void,
): Promise<ArchiveInfo> {
  if (file.size > 1024 ** 3) throw new Error("成品包不能超过 1 GiB");
  const tail = new Uint8Array(
    await file.slice(Math.max(0, file.size - 65557)).arrayBuffer(),
  );
  const tv = new DataView(tail.buffer);
  let end = -1;
  for (let i = tail.length - 22; i >= 0; i--)
    if (
      tv.getUint32(i, true) === 0x06054b50 &&
      i + 22 + tv.getUint16(i + 20, true) === tail.length
    ) {
      end = i;
      break;
    }
  if (end < 0)
    throw new Error("无法读取 ZIP 目录，请选择工具导出的 .source.zip");
  const count = tv.getUint16(end + 10, true),
    size = tv.getUint32(end + 12, true),
    offset = tv.getUint32(end + 16, true);
  if (
    count > 20000 ||
    size > 16 * 1024 ** 2 ||
    offset + size > file.size ||
    tv.getUint16(end + 4, true) !== 0
  )
    throw new Error("ZIP 目录超限或格式不支持");
  const cd = new Uint8Array(
      await file.slice(offset, offset + size).arrayBuffer(),
    ),
    v = new DataView(cd.buffer);
  let found:
    | { start: number; packed: number; unpacked: number; method: number }
    | undefined;
  for (let i = 0; i < cd.length;) {
    if (i + 46 > cd.length || v.getUint32(i, true) !== 0x02014b50)
      throw new Error("ZIP 目录损坏");
    const nameLength = v.getUint16(i + 28, true),
      next =
        i +
        46 +
        nameLength +
        v.getUint16(i + 30, true) +
        v.getUint16(i + 32, true);
    if (next > cd.length) throw new Error("ZIP 目录不完整");
    const name = new TextDecoder().decode(
      cd.subarray(i + 46, i + 46 + nameLength),
    );
    if (name === "package.json") {
      if (found) throw new Error("包中有重复的 package.json");
      if (v.getUint16(i + 8, true) & 1) throw new Error("不支持加密 ZIP");
      found = {
        start: v.getUint32(i + 42, true),
        packed: v.getUint32(i + 20, true),
        unpacked: v.getUint32(i + 24, true),
        method: v.getUint16(i + 10, true),
      };
    }
    i = next;
  }
  if (!found || found.packed > 512 * 1024 || found.unpacked > 512 * 1024)
    throw new Error("缺少或超限的 package.json");
  const header = new DataView(
    await file.slice(found.start, found.start + 30).arrayBuffer(),
  );
  if (header.byteLength !== 30 || header.getUint32(0, true) !== 0x04034b50)
    throw new Error("ZIP 文件头损坏");
  const start =
    found.start + 30 + header.getUint16(26, true) + header.getUint16(28, true);
  if (start + found.packed > offset) throw new Error("ZIP 内容范围无效");
  const packed = new Uint8Array(
    await file.slice(start, start + found.packed).arrayBuffer(),
  );
  const data =
    found.method === 0
      ? packed
      : found.method === 8
        ? inflateSync(packed, { out: new Uint8Array(found.unpacked) })
        : null;
  if (!data || data.length !== found.unpacked)
    throw new Error("无法解码制作包清单");
  const manifest = JSON.parse(new TextDecoder().decode(data));
  if (manifest.audience !== "private")
    throw new Error(
      "这个包没有专属定制标记（audience 不是 private）。请在 PSD 转换时指定当前需求，再重新打包；修改 ZIP 文件名不会改变归属。",
    );
  if (manifest.customizationRequestID !== requestID)
    throw new Error(
      `成品包绑定的需求与当前需求不同。包内需求：${manifest.customizationRequestID || "未填写"}；当前需求：${requestID}。请核对制作对象后重新转换。`,
    );
  if (manifest.templateBookID !== "custom-" + requestID)
    throw new Error(
      `包内书本标识与定制需求不一致。应为 custom-${requestID}；实际为 ${manifest.templateBookID || "未填写"}。请使用定制转换入口重新生成。`,
    );
  if (!Number.isInteger(manifest.packageVersion) || manifest.packageVersion < 1)
    throw new Error("源包版本不合法");
  const hash = await createSHA256();
  hash.init();
  for (let i = 0; i < file.size; i += 2 * 1024 ** 2) {
    hash.update(
      new Uint8Array(await file.slice(i, i + 2 * 1024 ** 2).arrayBuffer()),
    );
    progress(Math.min(1, (i + 2 * 1024 ** 2) / file.size));
  }
  return {
    sha: hash.digest(),
    title: manifest.title ?? "",
    packageVersion: manifest.packageVersion,
    pageCount: manifest.pages?.length ?? 0,
    requestID,
  };
}
