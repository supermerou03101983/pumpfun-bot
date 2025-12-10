#!/usr/bin/env bash
# Auto-deployment script with automated responses

set -e

cd /root/pumpfun-bot

# Create auto-response configuration
cat > /tmp/deploy_answers.txt <<EOF
your_helius_api_key_here
162.55.187.245
n
n
EOF

# Run deployment with auto-responses
bash deploy.sh < /tmp/deploy_answers.txt 2>&1 | tee /tmp/deploy.log

# Cleanup
rm -f /tmp/deploy_answers.txt
