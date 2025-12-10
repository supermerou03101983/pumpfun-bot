#!/usr/bin/env bash
# Quick verification script to check all files are in place

echo "🔍 PumpFun Bot - Setup Verification"
echo "===================================="
echo

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Check function
check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1 (MISSING)"
        return 1
    fi
}

check_dir() {
    if [ -d "$1" ]; then
        echo -e "${GREEN}✓${NC} $1/"
        return 0
    else
        echo -e "${RED}✗${NC} $1/ (MISSING)"
        return 1
    fi
}

# Check core files
echo "Core Files:"
check_file ".gitignore"
check_file "README.md"
check_file "FIRST_SETUP.md"
check_file "requirements.txt"
check_file "deploy.sh"
echo

# Check config
echo "Configuration:"
check_dir "config"
check_file "config/config.example.yaml"
echo

# Check source code
echo "Source Code:"
check_dir "src"
check_dir "src/core"
check_dir "src/utils"
check_dir "src/dashboard"
check_dir "src/tests"

check_file "src/__init__.py"
check_file "src/__main__.py"
check_file "src/main.py"

check_file "src/core/bonding_curve.py"
check_file "src/core/detector.py"
check_file "src/core/filters.py"
check_file "src/core/trader.py"
check_file "src/core/strategy.py"

check_file "src/utils/security.py"
check_file "src/utils/logger.py"
check_file "src/utils/health.py"
check_file "src/utils/paper_engine.py"

check_file "src/dashboard/app.py"

check_file "src/tests/test_filters.py"
check_file "src/tests/test_paper_engine.py"
echo

# Check scripts
echo "Scripts:"
check_dir "scripts"
check_file "scripts/encrypt_key.py"
check_file "scripts/simulate_trade.py"
echo

# Check systemd
echo "Systemd Services:"
check_dir "systemd"
check_file "systemd/pumpfun-bot.service"
check_file "systemd/pumpfun-dashboard.service"
echo

# Check executability
echo "Executable Permissions:"
if [ -x "deploy.sh" ]; then
    echo -e "${GREEN}✓${NC} deploy.sh is executable"
else
    echo -e "${RED}✗${NC} deploy.sh is not executable (run: chmod +x deploy.sh)"
fi

if [ -x "scripts/encrypt_key.py" ]; then
    echo -e "${GREEN}✓${NC} scripts/encrypt_key.py is executable"
else
    echo -e "${RED}✗${NC} scripts/encrypt_key.py is not executable"
fi

if [ -x "scripts/simulate_trade.py" ]; then
    echo -e "${GREEN}✓${NC} scripts/simulate_trade.py is executable"
else
    echo -e "${RED}✗${NC} scripts/simulate_trade.py is not executable"
fi
echo

# Count files
TOTAL_FILES=$(find . -type f -name "*.py" -o -name "*.sh" -o -name "*.yaml" -o -name "*.md" -o -name ".gitignore" | wc -l | xargs)

echo "===================================="
echo "Total files: $TOTAL_FILES"
echo
echo "Next steps:"
echo "  1. Read FIRST_SETUP.md for Git setup"
echo "  2. Run deploy.sh on your VPS"
echo "  3. Access dashboard at http://<vps-ip>:8501"
echo
echo "✅ Setup verification complete!"
