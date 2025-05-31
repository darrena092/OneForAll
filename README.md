
# One For All

One For All is software that was originally written and works best with with Helders  [Retro PSU](https://heldergametech.com/shop/gameboy-zero/retropsu/).

This software is designed to be used on Raspberry Pi handheld systems, such as the Gameboy Zero projects. This software handles battery monitoring, GPIO pins as control inputs, an analog joystick and safe shutdown. You will need specific hardware for some of these functions, which is listed below. The easiest way is to use Helders Retro PSU.

## Build instructions:  
  
### Install dependencies

* sudo apt-get install libraspberrypi-dev raspberrypi-kernel-headers libpng-dev

### Build

* git clone --recursive https://github.com/withgallantry/OneForAll.git  
  
* make  
  
## How to use it:  
  
* Install monitor script dependencies:
  - Adafruit_ADS1x15
  - uinput

* Configure (edit) the monitor script and config files accordingly to your hardware configuration.  
  
* sudo python monitor.py (or you can configure udev rules accordingly to avoid needing to run as root).