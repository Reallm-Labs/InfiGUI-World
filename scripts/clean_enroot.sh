#!/usr/bin/env bash
# 清理 enroot：停止&删除所有容器，删除自定义 enroot 数据目录
# 用法：sudo bash scripts/clean_enroot.sh [-f]
#   -f   强制删除 /zju_0038/enroot-* 目录而不提示

set -e

FORCE=0
while getopts "f" opt; do
  case $opt in
    f) FORCE=1 ;;
    *) echo "用法: $0 [-f]"; exit 1 ;;
  esac
done

# ───────────── 停止运行中的容器 ─────────────
RUNNING_CONTAINERS=$(enroot list -H || true)
if [[ -n "$RUNNING_CONTAINERS" ]]; then
  echo "➡️  停止运行中的 enroot 容器..."
  for C in $RUNNING_CONTAINERS; do
    echo "  • enroot stop $C"
    enroot stop "$C" || true
  done
else
  echo "✅ 没有正在运行的 enroot 容器"
fi

# ───────────── 删除所有容器 ─────────────
ALL_CONTAINERS=$(enroot list -a || true)
if [[ -n "$ALL_CONTAINERS" ]]; then
  echo "➡️  删除 enroot 容器镜像..."
  for C in $ALL_CONTAINERS; do
    echo "  • enroot rm $C"
    enroot rm "$C" || true
  done
else
  echo "✅ 没有 enroot 容器镜像需要删除"
fi

# ───────────── 删除自定义 enroot 数据目录 ─────────────
CUSTOM_DIRS=(/zju_0038/enroot-*)
if [[ ${#CUSTOM_DIRS[@]} -gt 0 ]]; then
  echo "➡️  检测到自定义 enroot 数据目录: ${CUSTOM_DIRS[*]}"
  if [[ $FORCE -eq 1 ]]; then
    rm -rf ${CUSTOM_DIRS[@]}
    echo "✅ 已强制删除自定义 enroot 数据目录"
  else
    read -p "是否删除上述目录? (y/N): " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
      rm -rf ${CUSTOM_DIRS[@]}
      echo "✅ 自定义 enroot 数据目录已删除"
    else
      echo "ℹ️  已跳过删除自定义 enroot 数据目录"
    fi
  fi
fi

echo "🎉 enroot 清理完成" 