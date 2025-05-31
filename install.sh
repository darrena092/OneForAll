#!/bin/bash

# Exit on error
set -e

# Check for root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root."
  exit 1
fi

# Copy files to /opt/OneForAll
echo "Copying files to /opt/OneForAll..."
mkdir -p /opt/OneForAll
cp -r . /opt/OneForAll

# Create systemd service
SERVICE_FILE="/etc/systemd/system/oneforall.service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=OFA Monitor Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/OneForAll/monitor.py
WorkingDirectory=/opt/OneForAll
StandardOutput=journal
StandardError=journal
Restart=on-failure
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
echo "Enabling and starting systemd service..."
systemctl daemon-reload
systemctl enable oneforall.service
systemctl restart oneforall.service

echo "Install complete."
