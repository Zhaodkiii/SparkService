import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ImageGalleryBlock } from "@/components/chat/blocks/MediaBlocks";
import type { ChatBlockDTO } from "@/types/chat";

function galleryBlock(images: Array<Record<string, unknown>>): ChatBlockDTO {
  return {
    id: "block-gallery",
    kind: "imageGallery",
    status: "ready",
    revision: 1,
    order_key: 1100,
    node_role: "timeline",
    payload: { image_gallery: { _0: { images } } },
  };
}

/** iOS 线上形态：_0 直接是图片数组（含 OCR text、file_md5 等额外字段）。 */
function iosGalleryBlock(images: Array<Record<string, unknown>>): ChatBlockDTO {
  return {
    id: "block-gallery-ios",
    kind: "imageGallery",
    status: "ready",
    revision: 1,
    order_key: 1,
    node_role: "timeline",
    payload: { image_gallery: { _0: images } },
  };
}

describe("ImageGalleryBlock", () => {
  it("渲染画廊容器与全部图片", () => {
    const block = galleryBlock([
      { url: "https://oss.example/a.webp", filename: "a.webp" },
      { url: "https://oss.example/b.webp", filename: "b.webp" },
    ]);
    const { container } = render(<ImageGalleryBlock block={block} />);
    expect(container.querySelector(".block--gallery")).not.toBeNull();
    expect(screen.getAllByRole("img")).toHaveLength(2);
  });

  it("单张加载失败显示占位卡与重试按钮，其他图片不受影响", () => {
    const block = galleryBlock([
      { url: "https://oss.example/a.webp", filename: "a.webp" },
      { url: "https://oss.example/b.webp", filename: "b.webp" },
    ]);
    render(<ImageGalleryBlock block={block} />);
    fireEvent.error(screen.getByRole("img", { name: "a.webp" }));

    expect(screen.getByText("图片加载失败")).toBeInTheDocument();
    expect(screen.getByText("a.webp")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试加载" })).toBeInTheDocument();
    // 另一张图片仍正常展示
    expect(screen.getByRole("img", { name: "b.webp" })).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(1);
  });

  it("点击重试加载恢复该图并追加 retry 参数", () => {
    const block = galleryBlock([{ url: "https://oss.example/a.webp", filename: "a.webp" }]);
    render(<ImageGalleryBlock block={block} />);
    fireEvent.error(screen.getByRole("img", { name: "a.webp" }));
    fireEvent.click(screen.getByRole("button", { name: "重试加载" }));

    const restored = screen.getByRole("img", { name: "a.webp" });
    expect(restored).toHaveAttribute("src", "https://oss.example/a.webp?retry=1");
    expect(screen.queryByText("图片加载失败")).not.toBeInTheDocument();
  });

  it("兼容 iOS 形态：_0 直接是图片数组，OCR text 不作为说明文字", () => {
    const block = iosGalleryBlock([
      { id: "29FF2C6F-C544-46D2-8FB1-2B90B21F5A53", url: "https://oss.example/ios.png", type: "image", file_id: 2568, file_md5: "abc", text: "OCR 识别出的整屏文字" },
    ]);
    const { container } = render(<ImageGalleryBlock block={block} />);
    expect(container.querySelector(".block--gallery")).not.toBeNull();
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(screen.queryByText("OCR 识别出的整屏文字")).not.toBeInTheDocument();
  });

  it("无文件名时占位卡显示图片数量", () => {
    const block = galleryBlock([{ url: "https://oss.example/a.webp" }]);
    render(<ImageGalleryBlock block={block} />);
    fireEvent.error(screen.getByRole("img", { name: "图片 1" }));
    expect(screen.getByText("共 1 张图片")).toBeInTheDocument();
  });
});
