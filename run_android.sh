#!/usr/bin/env bash
set -e

# ───────────── 参数解析 ─────────────
NAME=android-emulator          # -n 容器名
ADB_PORT=5037                  # -p ADB 端口
AVD_NAME=Pixel6_API33          # -d AVD 名称
DISABLE_KVM=0                  # -k 置位后关闭 KVM
HOST_SHARE_DIR="$PWD/share"    # -s 宿主机要挂进去的目录
CONT_SHARE_DIR="/mnt/share"    # -c 容器内目标目录
IMG=android-emulator.sqsh
AVD_DIR="$CONT_SHARE_DIR/.android"   # -a 自定义 AVD 数据目录

usage() {
  cat <<EOF
选项:
  -n NAME     容器名 (默认: android-emulator)
  -p PORT     ADB 端口 (默认: 5037)
  -d AVD      AVD 名称 (默认: Pixel6_API33)
  -k          关闭 KVM 直通 (软件加速)
  -s DIR      宿主机要挂载的目录 (默认: \$PWD/share)
  -c DIR      容器内挂载点 (默认: /mnt/share)
  -a DIR      自定义 AVD 数据目录 (默认: $CONT_SHARE_DIR/.android)
  -h          帮助
EOF
}

while getopts "n:p:d:ks:c:a:h" opt; do
  case $opt in
    n) NAME=$OPTARG ;;
    p) ADB_PORT=$OPTARG ;;
    d) AVD_NAME=$OPTARG ;;
    k) DISABLE_KVM=1 ;;
    s) HOST_SHARE_DIR=$OPTARG ;;
    c) CONT_SHARE_DIR=$OPTARG ;;
    a) AVD_DIR=$OPTARG ;;
    h) usage; exit 0 ;;
    *) usage; exit 1 ;;
  esac
done

[ -f "$IMG" ]      || { echo "❌ 找不到 $IMG"; exit 1; }
[ -d "$HOST_SHARE_DIR" ] || { echo "❌ 目录 $HOST_SHARE_DIR 不存在"; exit 1; }

# ───────────── KVM & 挂载选项 ─────────────
if [[ $DISABLE_KVM -eq 0 ]]; then
  echo "➡️  使用 KVM 加速"
  KVM_MOUNT_OPT="--mount /dev/kvm:/dev/kvm:bind"
  EMU_ACCEL_OPT="-accel on"
else
  echo "➡️  软件加速 (KVM 关闭)"
  KVM_MOUNT_OPT=""
  EMU_ACCEL_OPT="-accel off"
fi

SHARE_MOUNT_OPT="--mount ${HOST_SHARE_DIR}:${CONT_SHARE_DIR}"
ANDROID_ENV_OPT="--env ANDROID_SDK_HOME=${AVD_DIR} --env ANDROID_AVD_HOME=${AVD_DIR}/avd"

# ───────────── 第一次 create（若不存在）─────────────
if ! enroot list -a | grep -q "^${NAME}\$"; then
  echo "➜ enroot create $NAME ← $IMG"
  enroot create -n "$NAME" "$IMG"
fi

# ───────────── 启动容器 ─────────────
echo "➜ Starting enroot container '$NAME' (ADB @${ADB_PORT})"
enroot start \
  --rw \
  $KVM_MOUNT_OPT \
  $SHARE_MOUNT_OPT \
  $ANDROID_ENV_OPT \
  --env ADB_MDNS=0 \
  --env ADB_MDNS_OPENSCREEN=0 \
  "$NAME" -- /bin/bash -c "
    set -e
    export ANDROID_SDK_HOME=${AVD_DIR}
    export ANDROID_AVD_HOME=${AVD_DIR}/avd
    mkdir -p \$ANDROID_AVD_HOME
    # 首次自动创建 AVD
    if [ ! -d \$ANDROID_AVD_HOME/${AVD_NAME}.avd ]; then
      echo '⌚ 正在创建 AVD ...'
      avdmanager create avd -n $AVD_NAME \
        -k 'system-images;android-33;google_apis;x86_64' \
        -d 'pixel_6' -c 256M
    fi
    # 启动 ADB & Emulator
    adb start-server
    echo '✅ ADB 已启动；模拟器即将启动'
    emulator -avd $AVD_NAME -no-snapshot -no-boot-anim -no-window $EMU_ACCEL_OPT &
    echo '✅ 模拟器已启动，宿主机目录已挂载到 ${CONT_SHARE_DIR}'
    exec bash
  "