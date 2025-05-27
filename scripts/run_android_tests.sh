#!/bin/bash
set -e

echo "=============================================================="
echo "🤖 Android Real Tasks Test Suite"
echo "=============================================================="
echo "This script will run comprehensive Android automation tests."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
declare -a test_results
declare -a test_names

# Function to run a test and capture results
run_test() {
    local test_name="$1"
    local test_script="$2"
    local test_description="$3"
    
    echo ""
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}🧪 Running: $test_name${NC}"
    echo -e "${BLUE}📝 Description: $test_description${NC}"
    echo -e "${BLUE}================================================${NC}"
    
    # Set PYTHONPATH to include current directory for imports
    export PYTHONPATH="${PWD}:${PYTHONPATH}"
    
    if python3 "$test_script"; then
        echo -e "${GREEN}✅ $test_name: PASSED${NC}"
        test_results+=("PASSED")
    else
        echo -e "${RED}❌ $test_name: FAILED${NC}"
        test_results+=("FAILED")
    fi
    
    test_names+=("$test_name")
    
    # Wait a bit between tests to ensure cleanup
    echo "⏳ Waiting 10 seconds before next test..."
    sleep 10
}

# Function to print summary
print_summary() {
    echo ""
    echo "=============================================================="
    echo -e "${BLUE}📊 TEST SUMMARY${NC}"
    echo "=============================================================="
    
    local passed=0
    local failed=0
    
    for i in "${!test_names[@]}"; do
        local name="${test_names[$i]}"
        local result="${test_results[$i]}"
        
        if [ "$result" = "PASSED" ]; then
            echo -e "${GREEN}✅ $name: $result${NC}"
            ((passed++))
        else
            echo -e "${RED}❌ $name: $result${NC}"
            ((failed++))
        fi
    done
    
    echo ""
    echo "=============================================================="
    echo -e "${BLUE}📈 OVERALL RESULTS${NC}"
    echo "=============================================================="
    echo -e "✅ Passed: ${GREEN}$passed${NC}"
    echo -e "❌ Failed: ${RED}$failed${NC}"
    echo -e "📊 Total:  $((passed + failed))"
    
    if [ $failed -eq 0 ]; then
        echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
        return 0
    else
        echo -e "${RED}💥 SOME TESTS FAILED!${NC}"
        return 1
    fi
}

# Pre-flight checks
echo "🔍 Running pre-flight checks..."

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed or not in PATH${NC}"
    exit 1
fi

# Check if test files exist
test_files=(
    "tests/test_android_real_tasks.py"
    "tests/test_android_messaging.py"
    "tests/test_adb.py"
)

for file in "${test_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}❌ Test file not found: $file${NC}"
        exit 1
    fi
done

# Check if config exists
if [ ! -f "config.json" ]; then
    echo -e "${YELLOW}⚠️ config.json not found, tests will use default configuration${NC}"
fi

echo -e "${GREEN}✅ All pre-flight checks passed${NC}"

# Option to run specific test
if [ $# -eq 1 ]; then
    # Set PYTHONPATH to include current directory for imports
    export PYTHONPATH="${PWD}:${PYTHONPATH}"
    
    case "$1" in
        "adb")
            echo "🔧 Running ADB connectivity test only..."
            python3 tests/test_adb.py
            exit $?
            ;;
        "basic")
            echo "📱 Running basic Android tasks test only..."
            python3 tests/test_android_real_tasks.py
            exit $?
            ;;
        "messaging")
            echo "💬 Running messaging test only..."
            python3 tests/test_android_messaging.py
            exit $?
            ;;
        "help"|"-h"|"--help")
            echo "Usage: $0 [test_type]"
            echo ""
            echo "Available test types:"
            echo "  adb        - Run ADB connectivity test only"
            echo "  basic      - Run basic Android tasks test only"
            echo "  messaging  - Run messaging test only"
            echo "  (no args) - Run all tests in sequence"
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Unknown test type: $1${NC}"
            echo "Use '$0 help' to see available options"
            exit 1
            ;;
    esac
fi

# Run all tests in sequence
echo ""
echo "🚀 Starting full test suite..."
echo "⏰ This may take 10-20 minutes depending on emulator startup time."
echo ""

# Test 1: ADB Connectivity
run_test "ADB Connectivity" "tests/test_adb.py" "Basic ADB connection and device detection"

# Test 2: Basic Android Tasks
run_test "Basic Android Tasks" "tests/test_android_real_tasks.py" "Comprehensive Android UI automation tests"

# Test 3: Messaging and Communication
run_test "Messaging & Communication" "tests/test_android_messaging.py" "Phone calls, SMS, and contact management"

# Print final summary
echo ""
print_summary
exit_code=$?

# Cleanup message
echo ""
echo "🧹 Test suite completed. Check logs and screenshots for details."
echo "📸 Screenshots saved as: screenshot_*.png"
echo "📝 Logs available in: logs/"

exit $exit_code 