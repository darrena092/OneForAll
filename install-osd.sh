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
apt-get -y install python3 python3-uinput python3-pip libraspberrypi-dev raspberrypi-kernel-headers
pip3 install Adafruit_ADS1x15
# ------------------------------------------

# --------- Build OSD ---------------------
make -j4
#------------------------------------------

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
CONFIG_FILE="/boot/config.txt"
I2C_WAS_ALREADY_ENABLED=true

# Enable i2c_arm in config.txt
if grep -q '^\s*#\s*dtparam=i2c_arm=on' "$CONFIG_FILE"; then
    echo "Uncommenting i2c_arm..."
    sed -i 's/^\s*#\s*dtparam=i2c_arm=on/dtparam=i2c_arm=on/' "$CONFIG_FILE"
    I2C_WAS_ALREADY_ENABLED=false
elif ! grep -q '^\s*dtparam=i2c_arm=on' "$CONFIG_FILE"; then
    echo "Adding i2c_arm=on to config.txt..."
    echo 'dtparam=i2c_arm=on' >> "$CONFIG_FILE"
    I2C_WAS_ALREADY_ENABLED=false
fi

# Load i2c-dev module now
if ! lsmod | grep -q '^i2c_dev'; then
    echo "Loading i2c-dev kernel module..."
    modprobe i2c-dev
else
    echo "i2c-dev module already loaded."
fi

# Ensure it loads at boot
if ! grep -q '^i2c-dev' /etc/modules; then
    echo "Adding i2c-dev to /etc/modules..."
    echo 'i2c-dev' >> /etc/modules
else
    echo "i2c-dev already set to load at boot."
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
