#!/bin/bash
set -e

echo "===== Android Sandbox 依赖安装脚本 ====="
echo "此脚本将安装 Android SDK 工具和模拟器依赖项"

# 确保 apt 更新
echo "正在更新软件包列表..."
apt-get update

# 安装基本依赖
echo "正在安装基本依赖项..."
apt-get install -y \
    wget \
    unzip \
    openjdk-11-jdk \
    libgl1 \
    libpulse0 \
    libxcomposite1 \
    libxcursor1 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libasound2

# 创建 Android SDK 目录
ANDROID_SDK_ROOT="/opt/android-sdk"
mkdir -p "$ANDROID_SDK_ROOT"

# 下载并安装命令行工具
echo "正在下载 Android 命令行工具..."
cd /tmp
wget https://dl.google.com/android/repository/commandlinetools-linux-8092744_latest.zip
unzip commandlinetools-linux-8092744_latest.zip
mkdir -p "$ANDROID_SDK_ROOT/cmdline-tools/latest"
mv cmdline-tools/* "$ANDROID_SDK_ROOT/cmdline-tools/latest/"
rm -rf cmdline-tools commandlinetools-linux-8092744_latest.zip

# 设置环境变量
echo "正在设置环境变量..."
cat > /etc/profile.d/android-sdk.sh << EOF
export ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT"
export PATH="\$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:\$ANDROID_SDK_ROOT/platform-tools:\$ANDROID_SDK_ROOT/emulator:\$PATH"
EOF
source /etc/profile.d/android-sdk.sh

# 安装必要的 SDK 包
echo "正在安装 Android SDK 包..."
yes | sdkmanager --licenses
sdkmanager --install "platform-tools" "emulator" "platforms;android-33" "build-tools;33.0.2" "system-images;android-33;google_apis;x86_64"

# 创建默认的 AVD
echo "正在创建默认 AVD..."
echo "no" | avdmanager create avd \
  -n Pixel6_API33 \
  -k "system-images;android-33;google_apis;x86_64" \
  -d pixel_6 \
  -c 2048M

# 修改 AVD 配置以优化性能
echo "正在优化 AVD 配置..."
AVD_CONFIG="$HOME/.android/avd/Pixel6_API33.avd/config.ini"
if [[ -f "$AVD_CONFIG" ]]; then
    # 减少不必要的图形资源消耗
    echo "hw.gpu.enabled=yes" >> "$AVD_CONFIG"
    echo "hw.gpu.mode=swiftshader_indirect" >> "$AVD_CONFIG"
    echo "hw.ramSize=2048" >> "$AVD_CONFIG"
    echo "hw.lcd.density=440" >> "$AVD_CONFIG"
fi

echo "===== 安装完成 ====="
echo "可以使用以下命令启动模拟器："
echo "emulator -avd Pixel6_API33 -no-window"
echo "可以使用以下命令连接到设备："
echo "adb devices"
echo ""
echo "如需使得环境变量立即生效，请执行："
echo "source /etc/profile.d/android-sdk.sh"
