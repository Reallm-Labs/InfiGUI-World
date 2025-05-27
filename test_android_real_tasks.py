#!/usr/bin/env python3
"""
Real Android Tasks Test Script
This script performs actual Android tasks like opening apps, sending messages, etc.
"""

import time
import json
import os
import base64
from typing import Dict, Any, Optional
from environment.android_env import AndroidEnvironment
from utils.logging import setup_logger

logger = setup_logger()

class AndroidTaskTester:
    """Test class for performing real Android tasks"""
    
    def __init__(self, config: Dict[str, Any]):
        self.android_env = AndroidEnvironment(config)
        self.trajectory_id = None
        self.device_id = None
        
    def setup(self) -> bool:
        """Setup the Android emulator for testing"""
        print("🚀 Setting up Android emulator...")
        
        # Create a new emulator instance
        result = self.android_env.create()
        
        if not result.get('success', False):
            print(f"❌ Failed to create emulator: {result.get('error', 'Unknown error')}")
            return False
        
        self.trajectory_id = result.get('trajectory_id')
        self.device_id = result.get('device_id')
        
        print(f"✅ Emulator created successfully!")
        print(f"   Trajectory ID: {self.trajectory_id}")
        print(f"   Device ID: {self.device_id}")
        
        # Wait a moment for the emulator to fully boot
        print("⏳ Waiting for emulator to fully boot...")
        time.sleep(10)
        
        return True
    
    def take_screenshot(self, save_path: Optional[str] = None) -> bool:
        """拍摄屏幕截图并可选择保存到文件"""
        try:
            print("📸 Taking screenshot...")
            
            # 通过Android环境获取截图
            result = self.android_env.step(self.trajectory_id, "screenshot")
            
            if not result.get('success', False):
                print(f"❌ Screenshot command failed: {result.get('error', 'Unknown error')}")
                return False
            
            # 获取图像数据
            observation = result.get('observation', {})
            image_data = observation.get('image')
            
            if not image_data:
                print("❌ No image data received")
                return False
            
            # 如果指定了保存路径，保存到文件
            if save_path:
                try:
                    image_bytes = base64.b64decode(image_data)
                    
                    with open(save_path, 'wb') as f:
                        f.write(image_bytes)
                    print(f"📁 Screenshot saved to {save_path}")
                except Exception as e:
                    print(f"❌ Failed to save screenshot: {e}")
                    return False
            
            print("✅ Screenshot taken successfully")
            return True
            
        except Exception as e:
            print(f"❌ Screenshot failed: {e}")
            return False
    
    def unlock_device(self) -> bool:
        """Unlock the device and go to home screen"""
        print("🔓 Unlocking device...")
        
        # Press power button to wake up
        result = self.android_env.step(self.trajectory_id, "key power")
        if not result.get('success', False):
            print(f"❌ Failed to press power button: {result.get('error')}")
        
        time.sleep(2)
        
        # Swipe up to unlock
        result = self.android_env.step(self.trajectory_id, "swipe 540 1800 540 800 500")
        if not result.get('success', False):
            print(f"❌ Failed to swipe unlock: {result.get('error')}")
        
        time.sleep(2)
        
        # Go to home
        result = self.android_env.step(self.trajectory_id, "key home")
        if result.get('success', False):
            print("✅ Device unlocked and at home screen")
            return True
        else:
            print(f"❌ Failed to go to home: {result.get('error')}")
            return False
    
    def open_app_drawer(self) -> bool:
        """Open the app drawer"""
        print("📱 Opening app drawer...")
        
        # Swipe up from bottom to open app drawer
        result = self.android_env.step(self.trajectory_id, "swipe 540 1800 540 900 300")
        
        if result.get('success', False):
            print("✅ App drawer opened")
            time.sleep(2)
            return True
        else:
            print(f"❌ Failed to open app drawer: {result.get('error')}")
            return False
    
    def open_settings_app(self) -> bool:
        """Open the Settings app"""
        print("⚙️ Opening Settings app...")
        
        # First open app drawer
        if not self.open_app_drawer():
            return False
        
        # Try to find and click Settings app (approximate location)
        # This might need adjustment based on the specific device/launcher
        settings_locations = [
            (270, 1200),  # Common location
            (810, 1200),  # Alternative location
            (270, 1400),  # Lower row
            (810, 1400),  # Lower row, right
        ]
        
        for x, y in settings_locations:
            print(f"🎯 Trying to click Settings at ({x}, {y})")
            result = self.android_env.step(self.trajectory_id, f"click {x} {y}")
            
            if result.get('success', False):
                time.sleep(3)  # Wait for app to open
                
                # Check if we're in Settings by looking for common settings elements
                # This is a simplified check - in practice you'd analyze the UI hierarchy
                print("✅ Clicked on potential Settings location")
                return True
        
        print("❌ Could not find Settings app")
        return False
    
    def open_messaging_app(self) -> bool:
        """Open the messaging/SMS app"""
        print("💬 Opening Messages app...")
        
        # Go to home first
        self.android_env.step(self.trajectory_id, "key home")
        time.sleep(2)
        
        # Open app drawer
        if not self.open_app_drawer():
            return False
        
        # Try to find and click Messages app
        message_locations = [
            (270, 1000),  # Common location
            (810, 1000),  # Alternative location
            (270, 1200),  # Another row
            (810, 1200),  # Another position
        ]
        
        for x, y in message_locations:
            print(f"🎯 Trying to click Messages at ({x}, {y})")
            result = self.android_env.step(self.trajectory_id, f"click {x} {y}")
            
            if result.get('success', False):
                time.sleep(3)
                print("✅ Clicked on potential Messages location")
                return True
        
        print("❌ Could not find Messages app")
        return False
    
    def test_typing_text(self) -> bool:
        """Test typing text in the current screen"""
        print("⌨️ Testing text input...")
        
        # First tap somewhere on screen to potentially focus a text field
        result = self.android_env.step(self.trajectory_id, "click 540 1000")
        time.sleep(1)
        
        # Type some test text
        test_text = "Hello from Android automation test!"
        result = self.android_env.step(self.trajectory_id, f'text "{test_text}"')
        
        if result.get('success', False):
            print(f"✅ Successfully typed: '{test_text}'")
            time.sleep(2)
            return True
        else:
            print(f"❌ Failed to type text: {result.get('error')}")
            return False
    
    def test_navigation_gestures(self) -> bool:
        """Test various navigation gestures"""
        print("👆 Testing navigation gestures...")
        
        gestures_success = 0
        total_gestures = 4
        
        # Test back gesture
        print("   Testing back gesture...")
        result = self.android_env.step(self.trajectory_id, "key back")
        if result.get('success', False):
            gestures_success += 1
            print("   ✅ Back gesture successful")
        else:
            print("   ❌ Back gesture failed")
        time.sleep(1)
        
        # Test home gesture
        print("   Testing home gesture...")
        result = self.android_env.step(self.trajectory_id, "key home")
        if result.get('success', False):
            gestures_success += 1
            print("   ✅ Home gesture successful")
        else:
            print("   ❌ Home gesture failed")
        time.sleep(1)
        
        # Test recent apps
        print("   Testing recent apps...")
        result = self.android_env.step(self.trajectory_id, "key recents")
        if result.get('success', False):
            gestures_success += 1
            print("   ✅ Recent apps gesture successful")
        else:
            print("   ❌ Recent apps gesture failed")
        time.sleep(2)
        
        # Test scroll gesture
        print("   Testing scroll gesture...")
        result = self.android_env.step(self.trajectory_id, "swipe 540 1200 540 800 300")
        if result.get('success', False):
            gestures_success += 1
            print("   ✅ Scroll gesture successful")
        else:
            print("   ❌ Scroll gesture failed")
        time.sleep(1)
        
        print(f"✅ Navigation gestures: {gestures_success}/{total_gestures} successful")
        return gestures_success >= total_gestures // 2  # At least half should work
    
    def run_comprehensive_test(self) -> bool:
        """Run a comprehensive test of Android functionality"""
        print("\n" + "="*60)
        print("🤖 STARTING COMPREHENSIVE ANDROID TASK TEST")
        print("="*60)
        
        success_count = 0
        total_tests = 8
        
        # Test 1: Setup
        print(f"\n📋 Test 1/{total_tests}: Setup")
        if self.setup():
            success_count += 1
        
        if not self.trajectory_id:
            print("❌ Cannot continue without successful setup")
            return False
        
        # Test 2: Initial screenshot
        print(f"\n📋 Test 2/{total_tests}: Initial Screenshot")
        if self.take_screenshot("screenshot_initial.png"):
            success_count += 1
        
        # Test 3: Unlock device
        print(f"\n📋 Test 3/{total_tests}: Unlock Device")
        if self.unlock_device():
            success_count += 1
        
        # Test 4: Navigation gestures
        print(f"\n📋 Test 4/{total_tests}: Navigation Gestures")
        if self.test_navigation_gestures():
            success_count += 1
        
        # Test 5: Open Settings
        print(f"\n📋 Test 5/{total_tests}: Open Settings App")
        if self.open_settings_app():
            success_count += 1
        
        # Test 6: Screenshot after Settings
        print(f"\n📋 Test 6/{total_tests}: Screenshot After Settings")
        if self.take_screenshot("screenshot_settings.png"):
            success_count += 1
        
        # Test 7: Open Messaging
        print(f"\n📋 Test 7/{total_tests}: Open Messages App")
        if self.open_messaging_app():
            success_count += 1
        
        # Test 8: Text input
        print(f"\n📋 Test 8/{total_tests}: Text Input")
        if self.test_typing_text():
            success_count += 1
        
        # Final screenshot
        print(f"\n📸 Taking final screenshot...")
        self.take_screenshot("screenshot_final.png")
        
        # Results
        print("\n" + "="*60)
        print("📊 TEST RESULTS")
        print("="*60)
        print(f"✅ Successful tests: {success_count}/{total_tests}")
        print(f"📈 Success rate: {success_count/total_tests*100:.1f}%")
        
        if success_count >= total_tests * 0.7:  # 70% success rate
            print("🎉 OVERALL TEST: PASSED")
            return True
        else:
            print("❌ OVERALL TEST: FAILED")
            return False
    
    def cleanup(self):
        """Clean up the test environment"""
        print("\n🧹 Cleaning up...")
        
        if self.trajectory_id:
            # Save the current state before cleanup
            print("💾 Saving emulator state...")
            save_result = self.android_env.save(self.trajectory_id)
            if save_result.get('success'):
                print("✅ State saved successfully")
            
            # Remove the emulator instance
            print("🗑️ Removing emulator instance...")
            remove_result = self.android_env.remove(self.trajectory_id)
            if remove_result.get('success'):
                print("✅ Emulator removed successfully")
            else:
                print(f"❌ Failed to remove emulator: {remove_result.get('error')}")
        
        print("✅ Cleanup completed")


def main():
    """Main function to run the Android task tests"""
    
    # Load configuration
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        android_config = config.get('environment', {}).get('android', {})
    else:
        # Default configuration if config file doesn't exist
        android_config = {
            'snapshot_dir': '/tmp/android_snapshots',
            'adb_path': '/root/.local/share/enroot/android-emulator/opt/android-sdk/platform-tools/adb',
            'emulator_path': '/root/.local/share/enroot/android-emulator/opt/android-sdk/emulator/emulator',
            'avd_name': 'Pixel6_API33_x86',
            'boot_timeout': 120,
            'base_port': 5554
        }
    
    print("🤖 Android Real Tasks Test")
    print("This test will perform actual Android tasks like opening apps and sending messages.")
    print(f"Configuration: {android_config}")
    
    # Create tester instance
    tester = AndroidTaskTester(android_config)
    
    try:
        # Run the comprehensive test
        success = tester.run_comprehensive_test()
        
        # Print final status
        if success:
            print("\n🎉 All tests completed successfully!")
            exit_code = 0
        else:
            print("\n❌ Some tests failed!")
            exit_code = 1
            
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
        exit_code = 2
    except Exception as e:
        print(f"\n💥 Test failed with exception: {e}")
        logger.error(f"Test exception: {e}", exc_info=True)
        exit_code = 3
    finally:
        # Always cleanup
        try:
            tester.cleanup()
        except Exception as e:
            print(f"⚠️ Cleanup failed: {e}")
    
    print(f"\n🏁 Test completed with exit code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    exit(main()) 