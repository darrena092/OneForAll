
# One For All

One For All is software that was originally written and works best with with Helders  [Retro PSU](https://heldergametech.com/shop/gameboy-zero/retropsu/).

This software is designed to be used on Raspberry Pi handheld systems, such as the Gameboy Zero projects. This software handles battery monitoring, GPIO pins as control inputs, an analog joystick and safe shutdown. You will need specific hardware for some of these functions, which is listed below. The easiest way is to use Helders Retro PSU.

## Build instructions:  

## How to use it:  
  
* git clone --recursive https://github.com/darrena092/OneForAll.git  
* Edit the configuration files to match your keys.
* Modify the cmake command in install-display-driver.sh script to match your display. (Docs on which defines to use can be found at [https://github.com/juj/fbcp-ili9341](https://github.com/juj/fbcp-ili9341))
* `chmod +x install-osd.sh`
* `chmod +x install-display-driver.sh`
* `sudo ./install-osd.sh`
* `sudo ./install-display-driver.sh`
* Reboot when prompted.