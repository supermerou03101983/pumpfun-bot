#!/usr/bin/env bash
set -euo pipefail

################################################################################
# PumpFun Bot - Non-Interactive Deployment Script
# For automated deployment without user prompts
################################################################################

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
INSTALL_DIR="/opt/pumpfun-bot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Variables d'environnement (peuvent être définies avant d'exécuter le script)
HELIUS_API_KEY="${HELIUS_API_KEY:-your_helius_api_key_here}"
VPS_IP="${VPS_IP:-162.55.187.245}"

echo "════════════════════════════════════════════════════════════════"
echo "  PumpFun Bot - Non-Interactive Deployment"
echo "════════════════════════════════════════════════════════════════"
echo

# Vérifier si root
if [[ $EUID -ne 0 ]]; then
   log_error "Ce script doit être exécuté en tant que root (utilisez sudo)"
   exit 1
fi

# Détecter l'OS
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

# 1. Installation des dépendances système
log_info "Installing system dependencies..."
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq

# Détecter la version de Python disponible
if apt-cache show python3.12 >/dev/null 2>&1; then
    PYTHON_VERSION="3.12"
    log_info "Detected Python 3.12 (Ubuntu 24.04)"
elif apt-cache show python3.11 >/dev/null 2>&1; then
    PYTHON_VERSION="3.11"
    log_info "Detected Python 3.11 (Ubuntu 22.04)"
else
    PYTHON_VERSION="3"
    log_warn "Using default python3"
fi

apt-get install -y -qq \
    software-properties-common \
    build-essential \
    curl \
    git \
    redis-server \
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-venv \
    python${PYTHON_VERSION}-dev \
    python3-pip \
    jq \
    age \
    || { log_error "Failed to install system dependencies"; exit 1; }

# Créer le lien symbolique python3 si nécessaire
if [ "$PYTHON_VERSION" != "3" ]; then
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 1 2>/dev/null || true
fi

systemctl enable redis-server >/dev/null 2>&1
systemctl start redis-server

log_success "System dependencies installed (Python ${PYTHON_VERSION})"

# 2. Configuration du répertoire du projet
log_info "Setting up project directory..."

# Cloner le repo si nécessaire
if [[ ! -d "$INSTALL_DIR" ]]; then
    log_info "Cloning repository from GitHub..."
    git clone https://github.com/supermerou03101983/pumpfun-bot.git "$INSTALL_DIR" || {
        log_error "Failed to clone repository"
        exit 1
    }
    log_success "Repository cloned to $INSTALL_DIR"
elif [[ ! -f "$INSTALL_DIR/requirements.txt" ]]; then
    # Le dossier existe mais est vide, cloner dedans
    log_info "Cloning repository..."
    rm -rf "$INSTALL_DIR"
    git clone https://github.com/supermerou03101983/pumpfun-bot.git "$INSTALL_DIR" || {
        log_error "Failed to clone repository"
        exit 1
    }
    log_success "Repository cloned to $INSTALL_DIR"
else
    log_info "Directory $INSTALL_DIR already exists, pulling latest changes..."
    cd "$INSTALL_DIR"
    git pull origin main || log_warn "Could not pull latest changes (continuing anyway)"
fi

cd "$INSTALL_DIR"

mkdir -p "$INSTALL_DIR/config"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$HOME/.config/sops/age"
chmod 700 "$HOME/.config/sops/age"

log_success "Project directory ready at $INSTALL_DIR"

# 3. Environnement virtuel Python
log_info "Creating Python virtual environment..."

if [[ ! -d "venv" ]]; then
    python${PYTHON_VERSION} -m venv venv
    log_success "Virtual environment created with Python ${PYTHON_VERSION}"
else
    log_warn "Virtual environment already exists"
fi

source venv/bin/activate
pip install --upgrade pip setuptools wheel -q
pip install -r requirements.txt -q

log_success "Python dependencies installed"

# 4. Configuration age (génération de clés)
log_info "Setting up age encryption..."

AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
if [[ ! -f "$AGE_KEY_FILE" ]]; then
    log_info "Generating new age keypair..."
    age-keygen -o "$AGE_KEY_FILE" 2>/dev/null
    chmod 600 "$AGE_KEY_FILE"
    log_success "Age keypair generated at $AGE_KEY_FILE"
else
    log_warn "Age keypair already exists at $AGE_KEY_FILE"
fi

AGE_PUBLIC_KEY=$(grep "# public key:" "$AGE_KEY_FILE" | awk '{print $4}')
log_info "Age public key: $AGE_PUBLIC_KEY"

# 5. Configuration du bot
log_info "Configuring bot..."

CONFIG_FILE="$INSTALL_DIR/config/config.yaml"

if [[ ! -f "$CONFIG_FILE" ]]; then
    cp "$INSTALL_DIR/config/config.example.yaml" "$CONFIG_FILE"

    # Remplacer les valeurs
    sed -i "s/YOUR_HELIUS_API_KEY/$HELIUS_API_KEY/g" "$CONFIG_FILE"
    sed -i "s/YOUR_HELIUS_KEY/$HELIUS_API_KEY/g" "$CONFIG_FILE"
    sed -i "s/YOUR_VPS_IP/$VPS_IP/g" "$CONFIG_FILE"
    sed -i "s/age1qyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqsqzcwqr/$AGE_PUBLIC_KEY/g" "$CONFIG_FILE"

    chmod 600 "$CONFIG_FILE"
    log_success "Configuration saved to $CONFIG_FILE"
else
    log_warn "Config file already exists, skipping"
fi

# 6. Wallet (créer un wallet de test pour le mode paper)
log_info "Setting up test wallet for paper trading..."

ENCRYPTED_WALLET="$INSTALL_DIR/config/trading_wallet.enc"
if [[ ! -f "$ENCRYPTED_WALLET" ]]; then
    # Générer une clé de test pour le paper trading
    TEST_KEY="5J1F2Z3K4L5M6N7P8Q9R0S1T2U3V4W5X6Y7Z8A9B0C1D2E3F4G5H6I7J8K9L0M1N2P3Q4R5S6T7U8V9W0X1Y2Z"
    echo "$TEST_KEY" | age --encrypt --recipient "$AGE_PUBLIC_KEY" --output "$ENCRYPTED_WALLET"
    chmod 600 "$ENCRYPTED_WALLET"
    log_success "Test wallet created (paper trading only)"
else
    log_warn "Encrypted wallet already exists"
fi

# 7. Installation des services systemd
log_info "Installing systemd services..."

cp "$INSTALL_DIR/systemd/pumpfun-bot.service" /etc/systemd/system/
cp "$INSTALL_DIR/systemd/pumpfun-dashboard.service" /etc/systemd/system/

systemctl daemon-reload
systemctl enable pumpfun-bot.service >/dev/null 2>&1
systemctl enable pumpfun-dashboard.service >/dev/null 2>&1

log_success "Systemd services installed and enabled"

# 8. Démarrage des services
log_info "Starting services..."

systemctl restart pumpfun-bot.service || {
    log_error "Failed to start bot service"
    journalctl -u pumpfun-bot -n 20 --no-pager
    exit 1
}

sleep 2

systemctl restart pumpfun-dashboard.service || {
    log_error "Failed to start dashboard service"
    journalctl -u pumpfun-dashboard -n 20 --no-pager
    exit 1
}

log_success "Services started"

# 9. Configuration du pare-feu
log_info "Configuring firewall..."

if command -v ufw &> /dev/null; then
    ufw allow ssh >/dev/null 2>&1
    ufw allow 8501/tcp comment "PumpFun Dashboard" >/dev/null 2>&1
    ufw allow 8080/tcp comment "PumpFun Webhook" >/dev/null 2>&1

    if ! ufw status | grep -q "Status: active"; then
        echo "y" | ufw enable >/dev/null 2>&1
    fi

    log_success "Firewall configured (ports 8080, 8501 open)"
else
    log_warn "UFW not installed. Manually open ports 8080 and 8501 if needed."
fi

# 10. Résumé final
echo
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║  🚀  PumpFun Bot Deployment Complete!                          ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo
log_success "Installation directory: $INSTALL_DIR"
log_success "Configuration: $INSTALL_DIR/config/config.yaml"
log_success "Encrypted wallet: $INSTALL_DIR/config/trading_wallet.enc (TEST KEY)"
echo
log_info "📊 Dashboard: http://$VPS_IP:8501"
log_info "🔍 Health Check: curl http://localhost:8080/health"
echo
log_info "Service Status:"
systemctl status pumpfun-bot.service --no-pager -l | grep "Active:" || true
systemctl status pumpfun-dashboard.service --no-pager -l | grep "Active:" || true
echo
log_info "View Logs:"
echo "  Bot:       journalctl -u pumpfun-bot -f"
echo "  Dashboard: journalctl -u pumpfun-dashboard -f"
echo
log_warn "Trading Mode: PAPER (simulated trades only)"
log_warn "Test wallet configured - Replace with real key for live trading"
echo
log_success "Deployment complete! 🎉"
echo
