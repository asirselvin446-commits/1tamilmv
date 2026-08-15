#!/usr/bin/env bash
set -e

echo "==============================================="
echo "   1TamilVT-TG Linux VPS 24/7 Deployment      "
echo "==============================================="

APP_DIR=$(pwd)

# Check root
if [ "$EUID" -ne 0 ]; then
  echo "⚠️ Please run as root (sudo bash deploy_vps.sh)"
  exit 1
fi

echo "📦 Installing system dependencies..."
apt-get update -y
apt-get install -y python3 python3-pip python3-venv

echo "🔧 Setting up Python virtual environment..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "⚙️ Creating systemd service..."
cat <<EOF > /etc/systemd/system/tamilbot.service
[Unit]
Description=1TamilVT-TG Telegram Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python -m bot
Restart=always
RestartSec=10
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now tamilbot.service

echo ""
echo "✅ 1TamilVT-TG Bot is now running 24/7 as a system service!"
echo "• View live logs: journalctl -u tamilbot -f"
echo "• Check status:   systemctl status tamilbot"
echo "• Restart bot:    systemctl restart tamilbot"
echo "• Stop bot:       systemctl stop tamilbot"
