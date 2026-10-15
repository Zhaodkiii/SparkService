#!/usr/bin/env bash
# Shared by the release entry point and the release skill. No network requests.
validate_release_target() {
  local source_dir="$1" target="$2" branch effective
  branch="$(git -C "$source_dir" symbolic-ref --quiet --short HEAD)" || {
    echo "发布阻止：无法确认源码分支（非 Git 仓库或 detached HEAD）。" >&2; return 2;
  }
  if [[ "$target" != "39.106.39.110" && "$target" != "root@39.106.39.110" ]]; then
    echo "发布阻止：当前分支 ${branch}，唯一允许的发布服务器是 39.106.39.110。" >&2
    echo "严禁将 TravelDiary 分支发布到 139.196.215.51；环境变量、SSH 别名或重试均不得绕过。" >&2
    return 2
  fi
  effective="$(ssh -G "$target" 2>/dev/null | awk '$1 == "hostname" {host=$2} END {print host}')" || {
    echo "发布阻止：无法解析 SSH 最终目标。" >&2; return 2;
  }
  if [[ "$effective" != "39.106.39.110" ]]; then
    echo "发布阻止：SSH HostName 未解析为 39.106.39.110，禁止远程操作。" >&2; return 2
  fi
  printf '发布目标校验通过：branch=%s，host=%s\n' "$branch" "$effective"
}
