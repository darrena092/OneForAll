#!/bin/bash

# Exit on error
set -e

# Check for root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root."
  exit 1
fi

# Stop the service if it's running
if systemctl is-active --quiet oneforall.service; then
    echo "Stopping running service..."
    systemctl stop oneforall.service
fi

# --------- Install dependencies -----------
apt-get -y update
apt-get -y install python3 python3-uinput
pip3 install Adafruit_ADS1x15 --break-system-packages
# ------------------------------------------

# ---------- Ensure uinput is loaded ----------
if ! lsmod | grep -q '^uinput'; then
    echo "Loading uinput module..."
    modprobe uinput
else
    echo "uinput module already loaded."
fi

# Ensure uinput loads at boot
if ! grep -q '^uinput' /etc/modules; then
    echo "Adding uinput to /etc/modules..."
    echo 'uinput' | tee -a /etc/modules > /dev/null
else
    echo "uinput already set to load at boot."
fi
# --------------------------------------------

# ---------- Configure firmware ------------
CONFIG_FILE="/boot/firmware/config.txt"
I2C_WAS_ALREADY_ENABLED=true

if ! grep -q '^dtparam=i2c_arm=on' "$CONFIG_FILE"; then
    echo "Enabling i2c_arm..."
    echo 'dtparam=i2c_arm=on' | tee -a "$CONFIG_FILE"
    I2C_WAS_ALREADY_ENABLED=false
fi
# ------------------------------------------

# ---------- Install Monitor Service -------
# Copy files to /opt/OneForAll
echo "Copying files to /opt/OneForAll..."
mkdir -p /opt/OneForAll
cp -r . /opt/OneForAll

# Create systemd service for monitor script
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

# Enable the service
echo "Enabling OFA monitor service..."
systemctl daemon-reload
systemctl enable oneforall.service

# Only start service if i2c was already enabled
if [ "$I2C_WAS_ALREADY_ENABLED" = true ]; then
    echo "Starting OFA monitor service..."
    systemctl restart oneforall.service
else
    echo "i2c_arm was just enabled in config.txt."
    echo "Please reboot before starting the OFA monitor service."
fi
# ------------------------------------------

echo "Install complete."
