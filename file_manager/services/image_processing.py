"""智能体头像图片处理：校验、EXIF 纠正、1:1 裁剪与 1024×1024 WebP 输出。

所有校验失败以 ``AvatarProcessingError`` 抛出，消息为稳定错误码，
由 API 层映射为业务错误响应。绝不信任客户端扩展名与 Content-Type。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from file_manager.constants import (
    AVATAR_MAX_BYTES,
    AVATAR_MAX_DIMENSION,
    AVATAR_OUTPUT_SIZE,
)

# 透明像素合成背景色。
_ALPHA_BACKGROUND = (255, 255, 255)

_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class AvatarProcessingError(ValueError):
    """图片校验或处理失败；消息即错误码。"""


@dataclass(frozen=True)
class ProcessedAvatar:
    content: bytes
    width: int
    height: int
    file_md5: str


def validate_crop_params(*, crop_x: float, crop_y: float, crop_size: float) -> None:
    values = (crop_x, crop_y, crop_size)
    if any(not isinstance(value, (int, float)) or value != value for value in values):  # NaN 检查
        raise AvatarProcessingError("AVATAR_CROP_INVALID")
    if crop_x < 0 or crop_y < 0 or crop_size <= 0:
        raise AvatarProcessingError("AVATAR_CROP_INVALID")
    if crop_x > 1 or crop_y > 1 or crop_size > 1:
        raise AvatarProcessingError("AVATAR_CROP_INVALID")
    if crop_x + crop_size > 1 or crop_y + crop_size > 1:
        raise AvatarProcessingError("AVATAR_CROP_INVALID")


def build_agent_avatar(raw: bytes, *, crop_x: float, crop_y: float, crop_size: float) -> ProcessedAvatar:
    """把原始图片字节处理为 1024×1024 WebP，返回内容与元数据。"""
    if not raw:
        raise AvatarProcessingError("AVATAR_FORMAT_INVALID")
    if len(raw) > AVATAR_MAX_BYTES:
        raise AvatarProcessingError("AVATAR_FILE_TOO_LARGE")
    validate_crop_params(crop_x=crop_x, crop_y=crop_y, crop_size=crop_size)

    try:
        with Image.open(BytesIO(raw)) as probe:
            if (probe.format or "").upper() not in _ALLOWED_FORMATS:
                raise AvatarProcessingError("AVATAR_FORMAT_INVALID")
            probe.verify()
    except AvatarProcessingError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AvatarProcessingError("AVATAR_FORMAT_INVALID") from exc

    try:
        with Image.open(BytesIO(raw)) as source:
            if getattr(source, "n_frames", 1) != 1:
                raise AvatarProcessingError("AVATAR_ANIMATED_NOT_ALLOWED")
            image = ImageOps.exif_transpose(source)
            width, height = image.size
            if max(width, height) > AVATAR_MAX_DIMENSION:
                raise AvatarProcessingError("AVATAR_DIMENSION_EXCEEDED")

            left = round(crop_x * width)
            top = round(crop_y * height)
            side = round(crop_size * min(width, height))
            if side <= 0 or left < 0 or top < 0 or left + side > width or top + side > height:
                raise AvatarProcessingError("AVATAR_CROP_INVALID")

            cropped = image.crop((left, top, left + side, top + side))
            if cropped.mode in ("RGBA", "LA", "PA") or (cropped.mode == "P" and "transparency" in cropped.info):
                rgba = cropped.convert("RGBA")
                background = Image.new("RGB", rgba.size, _ALPHA_BACKGROUND)
                background.paste(rgba, mask=rgba.getchannel("A"))
                cropped = background
            else:
                cropped = cropped.convert("RGB")

            output = cropped.resize((AVATAR_OUTPUT_SIZE, AVATAR_OUTPUT_SIZE), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            # 不传入 exif/icc_profile，输出即剥离元数据。
            output.save(buffer, format="WEBP", quality=88, method=6)
            content = buffer.getvalue()
    except AvatarProcessingError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AvatarProcessingError("AVATAR_FORMAT_INVALID") from exc

    return ProcessedAvatar(
        content=content,
        width=AVATAR_OUTPUT_SIZE,
        height=AVATAR_OUTPUT_SIZE,
        file_md5=hashlib.md5(content).hexdigest(),
    )
