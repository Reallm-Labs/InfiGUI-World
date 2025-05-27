#!/usr/bin/env python3
"""
Android Messaging Tasks Test Script
This script focuses on messaging and communication tasks like sending SMS, opening contacts, etc.
"""

import time
import json
import os
import re
from typing import Dict, Any, Optional, List
from environment.android_env import AndroidEnvironment
from utils.logging import setup_logger

logger = setup_logger()

class AndroidMessagingTester:
    """Test class specifically for Android messaging and communication tasks"""
    
    def __init__(self, config: Dict[str, Any]):
        self.android_env = AndroidEnvironment(config)
        self.trajectory_id = None
        self.device_id = None
        
    def setup(self) -> bool:
        """Setup the Android emulator for testing"""
        print("🚀 Setting up Android emulator for messaging tests...")
        
        result = self.android_env.create()
        
        if not result.get('success', False):
            print(f"❌ Failed to create emulator: {result.get('error', 'Unknown error')}")
            return False
        
        self.trajectory_id = result.get('trajectory_id')
        self.device_id = result.get('device_id')
        
        print(f"✅ Emulator created successfully!")
        print(f"   Trajectory ID: {self.trajectory_id}")
        print(f"   Device ID: {self.device_id}")
        
        # Wait for emulator to fully boot
        print("⏳ Waiting for emulator to fully boot...")
        time.sleep(15)
        
        return True
    
    def get_ui_elements(self) -> List[Dict[str, Any]]:
        """Get current UI elements for analysis"""
        try:
            # Take a step that returns UI information
            result = self.android_env.step(self.trajectory_id, "screenshot")
            if result.get('success', False):
                observation = result.get('observation', {})
                ui_elements = observation.get('ui_elements', [])
                return ui_elements
        except Exception as e:
            print(f"❌ Failed to get UI elements: {e}")
        
        return []
    
    def find_element_by_text(self, target_text: str, partial_match: bool = True) -> Optional[Dict[str, Any]]:
        """Find UI element by text content"""
        ui_elements = self.get_ui_elements()
        
        for element in ui_elements:
            element_text = element.get('text', '').lower()
            target_lower = target_text.lower()
            
            if partial_match:
                if target_lower in element_text:
                    return element
            else:
                if element_text == target_lower:
                    return element
        
        return None
    
    def find_element_by_resource_id(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """Find UI element by resource ID"""
        ui_elements = self.get_ui_elements()
        
        for element in ui_elements:
            if resource_id in element.get('resource_id', ''):
                return element
        
        return None
    
    def click_element(self, element: Dict[str, Any]) -> bool:
        """Click on a UI element"""
        bounds = element.get('bounds')
        if not bounds or len(bounds) != 4:
            return False
        
        # Calculate center of element
        x = (bounds[0] + bounds[2]) // 2
        y = (bounds[1] + bounds[3]) // 2
        
        result = self.android_env.step(self.trajectory_id, f"click {x} {y}")
        return result.get('success', False)
    
    def unlock_and_home(self) -> bool:
        """Unlock device and go to home screen"""
        print("🔓 Unlocking device and going to home...")
        
        # Wake up device
        self.android_env.step(self.trajectory_id, "key power")
        time.sleep(2)
        
        # Swipe up to unlock
        self.android_env.step(self.trajectory_id, "swipe 540 1800 540 800 500")
        time.sleep(2)
        
        # Go to home
        result = self.android_env.step(self.trajectory_id, "key home")
        time.sleep(2)
        
        return result.get('success', False)
    
    def open_phone_app(self) -> bool:
        """Open the Phone/Dialer app"""
        print("📞 Opening Phone app...")
        
        # Try multiple methods to open phone app
        methods = [
            # Method 1: Try opening through app drawer
            lambda: self._open_app_from_drawer("phone", "dialer", "call"),
            
            # Method 2: Try using intent-like approach (some launchers support this)
            lambda: self._try_click_locations([(270, 1800), (540, 1800), (810, 1800)]),  # Bottom dock
            
            # Method 3: Search in app drawer
            lambda: self._search_and_open_app("phone")
        ]
        
        for method in methods:
            if method():
                print("✅ Phone app opened successfully")
                time.sleep(3)
                return True
        
        print("❌ Could not open Phone app")
        return False
    
    def open_messages_app(self) -> bool:
        """Open the Messages/SMS app"""
        print("💬 Opening Messages app...")
        
        methods = [
            lambda: self._open_app_from_drawer("message", "sms", "text"),
            lambda: self._try_click_locations([(270, 1800), (540, 1800), (810, 1800)]),  # Bottom dock
            lambda: self._search_and_open_app("messages")
        ]
        
        for method in methods:
            if method():
                print("✅ Messages app opened successfully")
                time.sleep(3)
                return True
        
        print("❌ Could not open Messages app")
        return False
    
    def open_contacts_app(self) -> bool:
        """Open the Contacts app"""
        print("👥 Opening Contacts app...")
        
        methods = [
            lambda: self._open_app_from_drawer("contact", "people"),
            lambda: self._search_and_open_app("contacts")
        ]
        
        for method in methods:
            if method():
                print("✅ Contacts app opened successfully")
                time.sleep(3)
                return True
        
        print("❌ Could not open Contacts app")
        return False
    
    def _open_app_from_drawer(self, *app_keywords) -> bool:
        """Try to open app from app drawer using keywords"""
        # Open app drawer
        self.android_env.step(self.trajectory_id, "swipe 540 1800 540 900 300")
        time.sleep(2)
        
        # Try clicking on various positions looking for the app
        app_positions = [
            (270, 1000), (540, 1000), (810, 1000),  # First row
            (270, 1200), (540, 1200), (810, 1200),  # Second row
            (270, 1400), (540, 1400), (810, 1400),  # Third row
        ]
        
        for x, y in app_positions:
            result = self.android_env.step(self.trajectory_id, f"click {x} {y}")
            if result.get('success', False):
                time.sleep(2)
                # Check if we opened an app (simple heuristic)
                current_ui = self.get_ui_elements()
                if len(current_ui) > 5:  # Assume app opened if many UI elements
                    return True
        
        return False
    
    def _try_click_locations(self, locations: List[tuple]) -> bool:
        """Try clicking on a list of locations"""
        for x, y in locations:
            result = self.android_env.step(self.trajectory_id, f"click {x} {y}")
            if result.get('success', False):
                time.sleep(2)
                return True
        return False
    
    def _search_and_open_app(self, app_name: str) -> bool:
        """Try to search for and open an app"""
        # This is a simplified implementation
        # In practice, you'd need to interact with the search widget
        
        # Open app drawer
        self.android_env.step(self.trajectory_id, "swipe 540 1800 540 900 300")
        time.sleep(2)
        
        # Try typing the app name (if search is available)
        result = self.android_env.step(self.trajectory_id, f'text "{app_name}"')
        time.sleep(2)
        
        # Try clicking in the center (where search results might appear)
        result = self.android_env.step(self.trajectory_id, "click 540 1000")
        time.sleep(2)
        
        return result.get('success', False)
    
    def test_make_call(self, phone_number: str = "123-456-7890") -> bool:
        """Test making a phone call"""
        print(f"📞 Testing phone call to {phone_number}...")
        
        if not self.open_phone_app():
            return False
        
        # Try to find and click on dialpad/keypad
        dialpad_keywords = ["dialpad", "keypad", "dial"]
        for keyword in dialpad_keywords:
            element = self.find_element_by_text(keyword)
            if element:
                self.click_element(element)
                time.sleep(1)
                break
        
        # Type the phone number
        result = self.android_env.step(self.trajectory_id, f'text "{phone_number}"')
        if not result.get('success', False):
            print("❌ Failed to type phone number")
            return False
        
        time.sleep(2)
        
        # Try to find and click call button
        call_element = self.find_element_by_text("call", partial_match=True)
        if call_element:
            success = self.click_element(call_element)
            time.sleep(2)
            
            # End call immediately (don't actually make the call)
            end_call_element = self.find_element_by_text("end", partial_match=True)
            if end_call_element:
                self.click_element(end_call_element)
            else:
                # Try pressing back or home to cancel
                self.android_env.step(self.trajectory_id, "key back")
            
            print("✅ Call test completed (call ended immediately)")
            return success
        else:
            print("❌ Could not find call button")
            return False
    
    def test_send_sms(self, phone_number: str = "123-456-7890", message: str = "Hello from Android automation test!") -> bool:
        """Test sending an SMS message"""
        print(f"💬 Testing SMS to {phone_number}: '{message}'")
        
        if not self.open_messages_app():
            return False
        
        # Look for compose/new message button
        compose_keywords = ["compose", "new", "create", "+"]
        compose_element = None
        
        for keyword in compose_keywords:
            element = self.find_element_by_text(keyword)
            if element:
                compose_element = element
                break
        
        if compose_element:
            self.click_element(compose_element)
            time.sleep(2)
        else:
            # Try clicking floating action button (common location)
            self.android_env.step(self.trajectory_id, "click 920 1600")
            time.sleep(2)
        
        # Type phone number in "To" field
        # First try to find the "To" field
        to_element = self.find_element_by_text("to", partial_match=True)
        if to_element:
            self.click_element(to_element)
        else:
            # Try clicking near top where "To" field usually is
            self.android_env.step(self.trajectory_id, "click 540 400")
        
        time.sleep(1)
        
        # Type phone number
        result = self.android_env.step(self.trajectory_id, f'text "{phone_number}"')
        if not result.get('success', False):
            print("❌ Failed to type phone number")
            return False
        
        time.sleep(1)
        
        # Move to message field (usually by pressing tab or clicking)
        self.android_env.step(self.trajectory_id, "click 540 800")
        time.sleep(1)
        
        # Type message
        result = self.android_env.step(self.trajectory_id, f'text "{message}"')
        if not result.get('success', False):
            print("❌ Failed to type message")
            return False
        
        time.sleep(2)
        
        # Look for send button
        send_element = self.find_element_by_text("send", partial_match=True)
        if send_element:
            # Don't actually send - just simulate the action
            print("✅ SMS composition test completed (not actually sent)")
            # Go back instead of sending
            self.android_env.step(self.trajectory_id, "key back")
            return True
        else:
            print("❌ Could not find send button")
            return False
    
    def test_browse_contacts(self) -> bool:
        """Test browsing contacts"""
        print("👥 Testing contact browsing...")
        
        if not self.open_contacts_app():
            return False
        
        # Try scrolling through contacts
        scroll_success = 0
        for i in range(3):
            result = self.android_env.step(self.trajectory_id, "swipe 540 1200 540 800 300")
            if result.get('success', False):
                scroll_success += 1
            time.sleep(1)
        
        if scroll_success > 0:
            print(f"✅ Contact browsing test completed ({scroll_success}/3 scrolls successful)")
            return True
        else:
            print("❌ Could not scroll through contacts")
            return False
    
    def test_communication_features(self) -> bool:
        """Run comprehensive communication features test"""
        print("\n" + "="*60)
        print("📱 STARTING ANDROID MESSAGING & COMMUNICATION TEST")
        print("="*60)
        
        success_count = 0
        total_tests = 6
        
        # Test 1: Setup
        print(f"\n📋 Test 1/{total_tests}: Setup")
        if self.setup():
            success_count += 1
        
        if not self.trajectory_id:
            print("❌ Cannot continue without successful setup")
            return False
        
        # Test 2: Unlock and home
        print(f"\n📋 Test 2/{total_tests}: Unlock and Home")
        if self.unlock_and_home():
            success_count += 1
        
        # Test 3: Phone app and call test
        print(f"\n📋 Test 3/{total_tests}: Phone App and Call Test")
        if self.test_make_call():
            success_count += 1
        
        # Test 4: Messages app and SMS test
        print(f"\n📋 Test 4/{total_tests}: Messages App and SMS Test")
        if self.test_send_sms():
            success_count += 1
        
        # Test 5: Contacts app test
        print(f"\n📋 Test 5/{total_tests}: Contacts App Test")
        if self.test_browse_contacts():
            success_count += 1
        
        # Test 6: Final screenshot
        print(f"\n📋 Test 6/{total_tests}: Final Screenshot")
        screenshot_result = self.android_env.step(self.trajectory_id, "screenshot")
        if screenshot_result.get('success', False):
            success_count += 1
            print("✅ Final screenshot captured")
        
        # Results
        print("\n" + "="*60)
        print("📊 MESSAGING TEST RESULTS")
        print("="*60)
        print(f"✅ Successful tests: {success_count}/{total_tests}")
        print(f"📈 Success rate: {success_count/total_tests*100:.1f}%")
        
        if success_count >= total_tests * 0.6:  # 60% success rate for messaging tests
            print("🎉 MESSAGING TEST: PASSED")
            return True
        else:
            print("❌ MESSAGING TEST: FAILED")
            return False
    
    def cleanup(self):
        """Clean up the test environment"""
        print("\n🧹 Cleaning up messaging test...")
        
        if self.trajectory_id:
            # Save state
            save_result = self.android_env.save(self.trajectory_id)
            if save_result.get('success'):
                print("✅ Messaging test state saved")
            
            # Remove emulator
            remove_result = self.android_env.remove(self.trajectory_id)
            if remove_result.get('success'):
                print("✅ Emulator removed successfully")


def main():
    """Main function to run the messaging tests"""
    
    # Load configuration
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        android_config = config.get('environment', {}).get('android', {})
    else:
        android_config = {
            'snapshot_dir': '/tmp/android_snapshots',
            'adb_path': '/root/.local/share/enroot/android-emulator/opt/android-sdk/platform-tools/adb',
            'emulator_path': '/root/.local/share/enroot/android-emulator/opt/android-sdk/emulator/emulator',
            'avd_name': 'Pixel6_API33_x86',
            'boot_timeout': 120,
            'base_port': 5556  # Different port to avoid conflicts
        }
    
    print("📱 Android Messaging & Communication Test")
    print("This test will perform messaging tasks like calls, SMS, and contact browsing.")
    
    tester = AndroidMessagingTester(android_config)
    
    try:
        success = tester.test_communication_features()
        
        if success:
            print("\n🎉 Messaging tests completed successfully!")
            exit_code = 0
        else:
            print("\n❌ Some messaging tests failed!")
            exit_code = 1
            
    except KeyboardInterrupt:
        print("\n⚠️ Messaging test interrupted by user")
        exit_code = 2
    except Exception as e:
        print(f"\n💥 Messaging test failed with exception: {e}")
        logger.error(f"Messaging test exception: {e}", exc_info=True)
        exit_code = 3
    finally:
        try:
            tester.cleanup()
        except Exception as e:
            print(f"⚠️ Cleanup failed: {e}")
    
    print(f"\n🏁 Messaging test completed with exit code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    exit(main()) 