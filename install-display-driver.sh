#!/bin/bash

# Exit on error
set -e

# Check for root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root."
  exit 1
fi

# --------- Install dependencies -----------
apt-get -y update
apt-get -y install git cmake libraspberrypi-dev raspberrypi-kernel-headers
# ------------------------------------------

# --------- Fetch and build driver ---------
cd /opt

# Remove existing repo if present
if [ -d "fbcp-ili9341" ]; then
    echo "Removing existing fbcp-ili9341 directory..."
    rm -rf fbcp-ili9341
fi

# Clone fresh
git clone https://github.com/juj/fbcp-ili9341.git
cd fbcp-ili9341
mkdir build
cd build

# Configure and build
cmake .. -DILI9341=ON -DGPIO_TFT_DATA_CONTROL=24 -DGPIO_TFT_RESET_PIN=25 -DGPIO_TFT_BACKLIGHT=18 -DSPI_BUS_CLOCK_DIVISOR=30 -DSTATISTICS=0
make -j4

# Move binary to /usr/local/sbin
mv ./fbcp-ili9341 /usr/local/sbin/fbcp-ili9341
# ------------------------------------------

# ---------- Install the service -------
SERVICE_FILE="/etc/systemd/system/fbcp.service"

# Stop, disable and remove existing service if present
if systemctl list-units --full -all | grep -q "fbcp.service"; then
    echo "Existing fbcp.service found. Stopping and removing..."
    systemctl stop fbcp.service || true
    systemctl disable fbcp.service || true
    rm -f "$SERVICE_FILE"
fi

# Create systemd service for monitor script
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Fast Framebuffer Copy Service for the Raspberry Pi
StartLimitIntervalSec=10

[Service]
User=root
Type=simple
Restart=always
RestartSec=1
StartLimitBurst=2
ExecStart=/usr/local/sbin/fbcp-ili9341

[Install]
WantedBy=default.target
EOF

# Enable and start the service
echo "Enabling SPI LCD service..."
systemctl daemon-reload
systemctl enable fbcp.service
# ------------------------------------------

# ---------- Configure firmware ------------
CONFIG_FILE="/boot/config.txt"

# Use FKMS driver for dispmanx compatibility
sed -i 's/^dtoverlay=vc4-kms-v3d$/dtoverlay=vc4-fkms-v3d/' "$CONFIG_FILE"

# Check for existing HDMI config
if grep -qE '^\s*hdmi_(group|mode|cvt)\s*=' "$CONFIG_FILE"; then
    echo "HDMI configuration already present in $CONFIG_FILE."
    echo "You'll need to manually ensure it's set correctly for 320x240 @ 60Hz."
    echo "This script will not overwrite it to avoid breaking your setup."
else
    # Inject HDMI config block
    sed -i '/^dtoverlay=vc4-fkms-v3d$/a\
hdmi_group=2\nhdmi_mode=87\nhdmi_cvt=320 240 60 1 0 0 0\nhdmi_force_hotplug=1' "$CONFIG_FILE"
fi

# Ensure hdmi_force_hotplug=1 is present and correct
if grep -q '^hdmi_force_hotplug=' "$CONFIG_FILE"; then
    sed -i 's/^hdmi_force_hotplug=.*/hdmi_force_hotplug=1/' "$CONFIG_FILE"
elif ! grep -qE '^\s*hdmi_(group|mode|cvt)\s*=' "$CONFIG_FILE"; then
    # Already inserted with the block, do nothing
    :
else
    # HDMI settings existed, but hdmi_force_hotplug was missing – append it
    echo 'hdmi_force_hotplug=1' | tee -a "$CONFIG_FILE" > /dev/null
fi
# ------------------------------------------

# ---------- Reboot prompt ----------------
echo ""
read -rp "Installation done. Reboot now? [y/N] " answer
case "$answer" in
    [Yy]*) sudo reboot ;;
    *) echo "Reboot skipped. Please reboot manually later. Note that the SPI LCD driver will not start until rebooting." ;;
esac
# ------------------------------------------
