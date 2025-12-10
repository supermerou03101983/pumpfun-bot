#!/usr/bin/env bash
set -euo pipefail

################################################################################
# PumpFun Bot - One-Click Deployment Script
#
# Supports: Ubuntu 22.04 / 24.04
# Usage: sudo ./deploy.sh
#
# What this script does:
# 1. Detects environment (local VS Code or remote VPS)
# 2. Installs system dependencies (Python 3.11, Redis, age, etc.)
# 3. Sets up Python virtual environment
# 4. Generates age encryption keypair (if not exists)
# 5. Prompts for configuration (API keys, RPC endpoints)
# 6. Encrypts trading wallet
# 7. Installs systemd services
# 8. Starts bot + dashboard
################################################################################

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/pumpfun-bot"
CONFIG_DIR="$INSTALL_DIR/config"
LOGS_DIR="$INSTALL_DIR/logs"
AGE_KEY_DIR="$HOME/.config/sops/age"
AGE_KEY_FILE="$AGE_KEY_DIR/keys.txt"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root (use sudo)"
   exit 1
fi

# Detect OS
if [[ ! -f /etc/os-release ]]; then
    log_error "Cannot detect OS. Only Ubuntu 22.04/24.04 supported."
    exit 1
fi

source /etc/os-release
if [[ "$ID" != "ubuntu" ]] || [[ ! "$VERSION_ID" =~ ^(22.04|24.04)$ ]]; then
    log_error "Unsupported OS: $PRETTY_NAME. Only Ubuntu 22.04/24.04 supported."
    exit 1
fi

log_info "Detected OS: $PRETTY_NAME"

################################################################################
# Step 1: Install System Dependencies
################################################################################

install_system_deps() {
    log_info "Installing system dependencies..."

    export DEBIAN_FRONTEND=noninteractive

    apt-get update -qq
    apt-get install -y -qq \
        software-properties-common \
        build-essential \
        curl \
        git \
        redis-server \
        python3.11 \
        python3.11-venv \
        python3.11-dev \
        python3-pip \
        jq \
        age \
        || { log_error "Failed to install system dependencies"; exit 1; }

    # Start Redis
    systemctl enable redis-server
    systemctl start redis-server

    log_success "System dependencies installed"
}

################################################################################
# Step 2: Setup Project Directory
################################################################################

setup_project_dir() {
    log_info "Setting up project directory..."

    # If running from cloned repo, copy to /opt
    if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
        log_info "Copying project files to $INSTALL_DIR..."
        mkdir -p "$INSTALL_DIR"
        cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
        cd "$INSTALL_DIR"
    else
        cd "$INSTALL_DIR"
    fi

    # Create necessary directories
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOGS_DIR"
    mkdir -p "$AGE_KEY_DIR"

    # Set permissions
    chmod 700 "$AGE_KEY_DIR"

    log_success "Project directory ready at $INSTALL_DIR"
}

################################################################################
# Step 3: Python Virtual Environment
################################################################################

setup_venv() {
    log_info "Creating Python virtual environment..."

    cd "$INSTALL_DIR"

    if [[ ! -d "venv" ]]; then
        python3.11 -m venv venv
        log_success "Virtual environment created"
    else
        log_warn "Virtual environment already exists, skipping creation"
    fi

    # Activate and install dependencies
    source venv/bin/activate
    pip install --upgrade pip setuptools wheel -q
    pip install -r requirements.txt -q

    log_success "Python dependencies installed"
}

################################################################################
# Step 4: Age Encryption Setup
################################################################################

setup_age_encryption() {
    log_info "Setting up age encryption..."

    if [[ ! -f "$AGE_KEY_FILE" ]]; then
        log_info "Generating new age keypair..."
        age-keygen -o "$AGE_KEY_FILE" 2>/dev/null
        chmod 600 "$AGE_KEY_FILE"
        log_success "Age keypair generated at $AGE_KEY_FILE"
    else
        log_warn "Age keypair already exists at $AGE_KEY_FILE"
    fi

    # Extract public key
    AGE_PUBLIC_KEY=$(grep "# public key:" "$AGE_KEY_FILE" | awk '{print $4}')
    log_info "Age public key: $AGE_PUBLIC_KEY"

    # Update security.py with the public key
    SECURITY_FILE="$INSTALL_DIR/src/utils/security.py"
    if [[ -f "$SECURITY_FILE" ]]; then
        # This will be done when we create the file - placeholder for now
        log_info "Public key will be used for wallet encryption"
    fi
}

################################################################################
# Step 5: Configuration Wizard
################################################################################

configure_bot() {
    log_info "Starting configuration wizard..."

    CONFIG_FILE="$CONFIG_DIR/config.yaml"

    # Check if config already exists
    if [[ -f "$CONFIG_FILE" ]]; then
        read -p "Config file exists. Overwrite? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_warn "Keeping existing config"
            return 0
        fi
    fi

    # Copy template
    cp "$CONFIG_DIR/config.example.yaml" "$CONFIG_FILE"

    # Prompt for values
    echo ""
    log_info "Please provide the following configuration values:"
    echo ""

    # Helius API Key
    read -p "Helius API Key (from helius.dev): " HELIUS_KEY
    sed -i "s/YOUR_HELIUS_API_KEY/$HELIUS_KEY/g" "$CONFIG_FILE"
    sed -i "s/YOUR_HELIUS_KEY/$HELIUS_KEY/g" "$CONFIG_FILE"

    # VPS IP for webhook
    read -p "VPS Public IP (for webhooks): " VPS_IP
    sed -i "s/YOUR_VPS_IP/$VPS_IP/g" "$CONFIG_FILE"

    # Confirm paper mode
    echo ""
    log_warn "Trading mode is set to PAPER (simulated trades only)"
    log_info "To enable LIVE trading later:"
    log_info "  1. Edit $CONFIG_FILE and set trading_mode: live"
    log_info "  2. Export LIVE_MODE_CONFIRMED=true"
    log_info "  3. Restart the bot: systemctl restart pumpfun-bot"
    echo ""

    chmod 600 "$CONFIG_FILE"
    log_success "Configuration saved to $CONFIG_FILE"
}

################################################################################
# Step 6: Encrypt Trading Wallet
################################################################################

encrypt_wallet() {
    log_info "Setting up trading wallet..."

    ENCRYPTED_WALLET="$CONFIG_DIR/trading_wallet.enc"

    if [[ -f "$ENCRYPTED_WALLET" ]]; then
        log_warn "Encrypted wallet already exists at $ENCRYPTED_WALLET"
        return 0
    fi

    echo ""
    log_info "You need to provide your Solana private key for trading."
    log_warn "IMPORTANT: This key will be encrypted and stored securely."
    log_warn "The plaintext key will NEVER be saved to disk."
    echo ""

    read -p "Do you want to encrypt a wallet now? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ -n $REPLY ]]; then
        log_warn "Skipping wallet encryption. Run later: python scripts/encrypt_key.py"
        return 0
    fi

    # Run encryption script
    cd "$INSTALL_DIR"
    source venv/bin/activate
    python scripts/encrypt_key.py

    if [[ -f "$ENCRYPTED_WALLET" ]]; then
        chmod 600 "$ENCRYPTED_WALLET"
        log_success "Wallet encrypted successfully"
    else
        log_error "Wallet encryption failed"
        exit 1
    fi
}

################################################################################
# Step 7: Install Systemd Services
################################################################################

install_systemd_services() {
    log_info "Installing systemd services..."

    # Copy service files
    cp "$INSTALL_DIR/systemd/pumpfun-bot.service" /etc/systemd/system/
    cp "$INSTALL_DIR/systemd/pumpfun-dashboard.service" /etc/systemd/system/

    # Reload systemd
    systemctl daemon-reload

    # Enable services
    systemctl enable pumpfun-bot.service
    systemctl enable pumpfun-dashboard.service

    log_success "Systemd services installed and enabled"
}

################################################################################
# Step 8: Start Services
################################################################################

start_services() {
    log_info "Starting services..."

    # Start bot
    systemctl restart pumpfun-bot.service
    sleep 2

    if systemctl is-active --quiet pumpfun-bot.service; then
        log_success "Bot service started"
    else
        log_error "Bot service failed to start. Check logs: journalctl -u pumpfun-bot -xe"
        exit 1
    fi

    # Start dashboard
    systemctl restart pumpfun-dashboard.service
    sleep 2

    if systemctl is-active --quiet pumpfun-dashboard.service; then
        log_success "Dashboard service started"
    else
        log_error "Dashboard service failed to start. Check logs: journalctl -u pumpfun-dashboard -xe"
        exit 1
    fi
}

################################################################################
# Step 9: Firewall Configuration
################################################################################

configure_firewall() {
    log_info "Configuring firewall..."

    if command -v ufw &> /dev/null; then
        # Allow SSH (if not already allowed)
        ufw allow ssh

        # Allow dashboard
        ufw allow 8501/tcp comment "PumpFun Dashboard"

        # Allow webhook
        ufw allow 8080/tcp comment "PumpFun Webhook"

        # Enable firewall (if not already enabled)
        if ! ufw status | grep -q "Status: active"; then
            echo "y" | ufw enable
        fi

        log_success "Firewall configured (ports 8080, 8501 open)"
    else
        log_warn "UFW not installed. Manually open ports 8080 and 8501 if needed."
    fi
}

################################################################################
# Step 10: Display Summary
################################################################################

display_summary() {
    VPS_IP=$(hostname -I | awk '{print $1}')

    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                                                                ║"
    echo "║  🚀  PumpFun Bot Deployment Complete!                          ║"
    echo "║                                                                ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    log_success "Installation directory: $INSTALL_DIR"
    log_success "Configuration: $CONFIG_DIR/config.yaml"
    log_success "Encrypted wallet: $CONFIG_DIR/trading_wallet.enc"
    echo ""
    log_info "📊 Dashboard: http://$VPS_IP:8501"
    log_info "🔍 Health Check: curl http://localhost:8080/health"
    echo ""
    log_info "Service Status:"
    systemctl status pumpfun-bot.service --no-pager -l | grep "Active:"
    systemctl status pumpfun-dashboard.service --no-pager -l | grep "Active:"
    echo ""
    log_info "View Logs:"
    echo "  Bot:       journalctl -u pumpfun-bot -f"
    echo "  Dashboard: journalctl -u pumpfun-dashboard -f"
    echo ""
    log_warn "Trading Mode: PAPER (simulated trades only)"
    log_info "See README.md for enabling live trading"
    echo ""
    log_success "Deployment complete! 🎉"
    echo ""
}

################################################################################
# Main Execution
################################################################################

main() {
    log_info "Starting PumpFun Bot deployment..."
    echo ""

    install_system_deps
    setup_project_dir
    setup_venv
    setup_age_encryption
    configure_bot
    encrypt_wallet
    install_systemd_services
    start_services
    configure_firewall
    display_summary
}

# Run main function
main
