import { inspectArchive } from "./archive";
self.onmessage = async (
  event: MessageEvent<{ file: File; requestID: string }>,
) => {
  try {
    const info = await inspectArchive(
      event.data.file,
      event.data.requestID,
      (progress) => self.postMessage({ progress }),
    );
    self.postMessage({ info });
  } catch (e) {
    self.postMessage({
      error: e instanceof Error ? e.message : "无法读取制作包",
    });
  }
};
