#!/usr/bin/env bash
# 启动多个独立模拟器实例（前台运行，方便查看日志）
# 每个实例使用独立的 enroot 数据目录，互不干扰

PORTS=(5554 5560 5562)

for PORT in "${PORTS[@]}"; do
  NAME="android-${PORT}"
  ENROOT_BASE="/zju_0038/enroot-${PORT}"
  # 每个实例挂载独立的宿主共享目录，避免 AVD 数据冲突
  SHARE_DIR="/root/share-${PORT}"
  mkdir -p "${SHARE_DIR}"
  # 为每个实例使用不同的 AVD 名称
  AVD_NAME="Pixel6_API33_${PORT}"

  echo "======== 启动 ${NAME} (console ${PORT}) ========"
  bash scripts/run_android.sh -n "${NAME}" -e "${PORT}" -o "${ENROOT_BASE}" -s "${SHARE_DIR}" -d "${AVD_NAME}" &
  PIDS+=("$!")
done

# 等待所有子进程退出
wait "${PIDS[@]}"

echo "======== 所有模拟器已退出 ========"