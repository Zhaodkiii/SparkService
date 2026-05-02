import hashlib


# ------------------------------
# 版本号比较工具（语义化版本）
# ------------------------------
def compare_versions(v1: str, v2: str) -> int:
    """
    比较两个语义化版本号（如 1.2.3 vs 1.10.0）
    返回：
      -1 = v1  < v2
       0 = v1 == v2
       1 = v1  > v2
    """

    def parse(value: str) -> list[int]:
        """解析版本字符串为数字数组，自动校验合法性"""
        text = (value or "").strip()
        if not text:
            raise ValueError("empty_version")  # 空版本非法
        parts = text.split(".")
        # 检查是否所有分段都是非空数字
        if any(part == "" or not part.isdigit() for part in parts):
            raise ValueError(f"invalid_version:{value}")
        return [int(part) for part in parts]

    # 解析两个版本
    p1 = parse(v1)
    p2 = parse(v2)

    # 补 0 对齐长度（例如 1.2 → 1.2.0）
    max_len = max(len(p1), len(p2))
    p1.extend([0] * (max_len - len(p1)))
    p2.extend([0] * (max_len - len(p2)))

    # 逐段比较
    for left, right in zip(p1, p2):
        if left < right:
            return -1
        if left > right:
            return 1
    return 0


# ------------------------------
# 构建号比较工具（支持数字/字符串）
# ------------------------------
def compare_builds(b1: str, b2: str) -> int:
    """
    比较构建号（build），支持纯数字或字符串
    返回规则同 compare_versions
    """
    left = (b1 or "").strip()
    right = (b2 or "").strip()

    # 都为空 → 相等
    if not left and not right:
        return 0
    # 一方为空
    if not left:
        return -1
    if not right:
        return 1

    # 都是纯数字 → 按数字比较
    if left.isdigit() and right.isdigit():
        li = int(left)
        ri = int(right)
        return (li > ri) - (li < ri)

    # 否则按字符串字典序比较
    return (left > right) - (left < right)


# ------------------------------
# 判断客户端是否需要更新
# ------------------------------
def is_client_older(
        version: str,
        latest_version: str,
        build: str = "",
        latest_build: str = ""
) -> bool:
    """
    综合判断：当前客户端版本是否落后于服务端最新版本
    先比较版本号，版本号相同再比较构建号
    """
    # 1. 先比较主版本号
    version_cmp = compare_versions(version, latest_version)
    if version_cmp != 0:
        return version_cmp < 0  # 版本更小 → 需要更新

    # 2. 版本号相同 → 比较构建号
    if latest_build:
        return compare_builds(build, latest_build) < 0

    # 都相同 → 不用更新
    return False


# ------------------------------
# 灰度发布：设备分桶哈希计算
# ------------------------------
def calculate_device_bucket(device_id: str, bundle_id: str = "") -> int:
    """
    根据 device_id + bundle_id 计算稳定哈希分桶（0~99）
    同一设备永远落在同一个桶，保证灰度发布均匀稳定
    """
    seed = f"{bundle_id}:{device_id}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()  # SHA256 哈希
    return int(digest[:8], 16) % 100  # 取前8位 → 0~99


# ------------------------------
# 判断是否对当前设备显示灰度更新
# ------------------------------
def should_show_gradual_release(
        *,
        device_id: str,
        bundle_id: str,
        current_version: str,
        percentage: int,
        min_version: str = "",
) -> bool:
    """
    灰度发布核心逻辑：
    1. 百分比 0% → 不显示
    2. 百分比 100% → 全量显示
    3. 当前版本 < 灰度最低版本 → 不显示
    4. 设备哈希桶 < 百分比 → 显示灰度
    """
    # 灰度关闭
    if percentage <= 0:
        return False
    # 全量发布
    if percentage >= 100:
        return True
    # 版本未达到灰度要求
    if min_version and compare_versions(current_version, min_version) < 0:
        return False
    # 无设备ID无法灰度
    if not device_id:
        return False

    # 设备分桶命中灰度范围
    return calculate_device_bucket(device_id, bundle_id) < percentage


# ------------------------------
# 获取客户端真实 IP
# ------------------------------
def get_client_ip(request) -> str:
    """
    从请求头获取真实客户端 IP
    优先读取 X-Forwarded-For（经过代理/负载均衡）
    否则读取 REMOTE_ADDR
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()  # 取第一个IP
    return request.META.get("REMOTE_ADDR", "") or ""