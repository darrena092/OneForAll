#!/usr/bin/env python
# sudo apt-get install python-serial
#
# This file originates from Vascofazza's Retropie open OSD project.
# Author: Federico Scozzafava
#
# THIS HEADER MUST REMAIN WITH THIS FILE AT ALL TIMES
#
# This firmware is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This firmware is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this repo. If not, see <http://www.gnu.org/licenses/>.
#
import Adafruit_ADS1x15
import RPi.GPIO as gpio
import configparser
import logging
import logging.handlers
import os
import re
import signal
import sys
import _thread as thread
import time
import uinput
from subprocess import Popen, PIPE, check_output, check_call
from threading import Event

# Batt variables
voltscale = 118.0  # ADJUST THIS
currscale = 640.0
resdivmul = 4.0
resdivval = 1000.0
dacres = 20.47
dacmax = 4096.0

backlightSetting = 1024

batt_threshold = 4

temperature_max = 70.0
temperature_threshold = 5.0

# BT Variables
bt_state = 'UNKNOWN'

# Wifi variables
wifi_state = 'UNKNOWN'
wif = 0
wifi_off = 0
wifi_warning = 1
wifi_error = 2
wifi_1bar = 3
wifi_2bar = 4
wifi_3bar = 5


def str2bool(v):
    return v.lower() in ("yes", "true", "True", "1")


bin_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
osd_path = bin_dir + '/osd/osd'
rfkill_path = bin_dir + '/rfkill/rfkill'

# General Configuration
generalConfig = configparser.ConfigParser()
generalConfig.read(bin_dir + '/general.cfg')

general = generalConfig['GENERAL']

# Keys Configuration
keysConfig = configparser.ConfigParser(inline_comment_prefixes="#")
keysConfig.read(bin_dir + '/' + general['KEYS_CONFIG'])
hotkeys = keysConfig['HOTKEYS']

if generalConfig.has_option("GENERAL", "DEBUG"):
    logging.basicConfig(filename=bin_dir + '/osd.log', level=logging.DEBUG)

HOTKEYS = []
BUTTONS = []
KEYS = {}
PREVIOUS_KEYSTATES = {}
COMBO_CURRENT_KEYS = set()

KEY_COMBOS = {}

# GPIO Init
gpio.setwarnings(False)
gpio.setmode(gpio.BCM)

for key, pin in keysConfig.items('KEYS'):
    BUTTONS.append(int(pin))
    KEYS.update({int(pin): getattr(uinput, key.upper())})
    PREVIOUS_KEYSTATES.update({int(pin): 0})

for key, pinSet in keysConfig.items('COMBOS'):
    pins = set(map(int, pinSet.split(',')))
    KEY_COMBOS.update({frozenset(pins): getattr(uinput, key.upper())})

VOLUME_UP = int(hotkeys['VOLUME_UP'])
VOLUME_DOWN = int(hotkeys['VOLUME_DOWN'])
TOGGLE_WIFI = int(hotkeys['TOGGLE_WIFI'])
TOGGLE_BLE = int(hotkeys['TOGGLE_BLE'])
TOGGLE_JOYSTICK = int(hotkeys['TOGGLE_JOYSTICK'])
SHOW_OSD_KEY = int(hotkeys['OSD_SHOW'])
SHUTDOWN = int(general['SHUTDOWN_DETECT'])
SHOW_OVERLAY_HOTKEY_ONLY = str2bool(general['SHOW_OVERLAY_HOTKEY_ONLY'])

if generalConfig.has_option("GENERAL", "BACKLIGHT_PWM"):
    if str2bool(general['BACKLIGHT_PWM']):
        import wiringpi

        wiringpi.wiringPiSetupGpio()

        wiringpi.pinMode(13, wiringpi.OUTPUT)
        wiringpi.pinMode(13, wiringpi.PWM_OUTPUT)
        wiringpi.pwmWrite(13, backlightSetting)

        BRIGHTNESS_UP = int(hotkeys['BRIGHTNESS_UP'])
        BRIGHTNESS_DOWN = int(hotkeys['BRIGHTNESS_DOWN'])

if generalConfig.has_option("GENERAL", "SENSOR_DETECT"):
    SENSOR_DETECT = int(general['SENSOR_DETECT'])
else:
    SENSOR_DETECT = -1

if keysConfig.has_option("HOTKEYS", "SAFE_SHUTDOWN"):
    SAFE_SHUTDOWN = int(hotkeys['SAFE_SHUTDOWN'])
else:
    SAFE_SHUTDOWN = -1

if keysConfig.has_option("HOTKEYS", "QUICKSAVE"):
    QUICKSAVE = int(hotkeys['QUICKSAVE'])
else:
    QUICKSAVE = -1

if keysConfig.has_option("HOTKEYS", "QUICKSAVE"):
    KEYS.update({int(QUICKSAVE): uinput.KEY_F2})
    KEYS.update({int(99): uinput.KEY_F4})

# Joystick Hardware settings
joystickConfig = keysConfig['JOYSTICK']  # TODO: Make this go to keys
DZONE = int(joystickConfig['DEADZONE'])  # dead zone applied to joystick (mV)
VREF = int(joystickConfig['VCC'])  # joystick Vcc (mV)
JOYSTICK_ENABLED = joystickConfig['ENABLED']

if JOYSTICK_ENABLED == 'True':
    KEYS.update({10001: uinput.ABS_X + (0, VREF, 0, 0),
                 10002: uinput.ABS_Y + (0, VREF, 0, 0), })

# Battery config
battery = generalConfig['BATTERY']
monitoring_enabled = str2bool(battery['ENABLED'])
batt_full = int(battery['FULL_BATT_VOLTAGE'])
batt_low = int(battery['BATT_LOW_VOLTAGE'])
batt_shdn = int(battery['BATT_SHUTDOWN_VOLT'])

BOUNCE_TIME = 0.03  # Debounce time in seconds

# GPIO Init
gpio.setup(BUTTONS, gpio.IN, pull_up_down=gpio.PUD_UP)

if not SHUTDOWN == -1:
    gpio.setup(SHUTDOWN, gpio.IN, pull_up_down=gpio.PUD_UP)

if not SENSOR_DETECT == -1:
    gpio.setup(SENSOR_DETECT, gpio.IN, pull_up_down=gpio.PUD_UP)

if keysConfig.has_option("HOTKEYS", "QUICKSAVE"):
    gpio.setup(int(QUICKSAVE), gpio.IN, pull_up_down=gpio.PUD_UP)

# Global Variables
global brightness
global volt
global info
global wifi
global volume
global charge
global bat
global joystick
global bluetooth
global lowbattery
global LAST_TRIGGERED_COMBO
LAST_TRIGGERED_COMBO = None

brightness = -1
info = False
volt = 410
volume = 1
wifi = 2
charge = 0
bat = 0
last_bat_read = 450
joystick = False
showOverlay = False
lowbattery = 0
overrideCounter = Event()

if JOYSTICK_ENABLED == 'True':
    joystick = True

# TO DO REPLACE A LOT OF OLD CALLS WITH THE CHECK_OUTPUT
if monitoring_enabled:
    adc = Adafruit_ADS1x15.ADS1015(address=0x48, busnum=1)
else:
    adc = False

device = uinput.Device(KEYS.values(), name="OneForAll", version=0x3)

time.sleep(1)


def hotkeyAction(key):
    if key == QUICKSAVE:
        return True

    if not gpio.input(SHOW_OSD_KEY) or (key == SHOW_OSD_KEY):
        if key in HOTKEYS:
            return True

    return False


def handle_sensor(pin):
    command = "backlight"
    if generalConfig.has_option("GENERAL", "SENSOR_COMMAND"):
        command = general['SENSOR_COMMAND']

    if command == "backlight":
        global backlightSetting
        state = 0 if gpio.input(pin) else 1
        if state == 1:
            wiringpi.pwmWrite(13, 0)
        if state == 0:
            wiringpi.pwmWrite(13, backlightSetting)

    if command == "shutdown":
        device.emit(uinput.KEY_SPACE, state)
        device.emit(uinput.KEY_F2, state)
        doShutdown()


def handle_quicksave(pin):
    logging.debug("Handling QUICKSAVE press")
    state = 0 if gpio.input(pin) else 1
    if not gpio.input(SHOW_OSD_KEY):
        logging.debug("Loading Game")
        device.emit(uinput.KEY_SPACE, state)
        device.emit(uinput.KEY_F4, state)
        device.syn()
    if gpio.input(SHOW_OSD_KEY):
        logging.debug("Saving Game")
        device.emit(uinput.KEY_SPACE, state)
        device.emit(uinput.KEY_F2, state)
        device.syn()


def handle_button(pin):
    global showOverlay
    global info
    global LAST_TRIGGERED_COMBO
    time.sleep(BOUNCE_TIME)
    state = 0 if gpio.input(pin) else 1

    if state == 1:
        COMBO_CURRENT_KEYS.add(pin)
    else:
        COMBO_CURRENT_KEYS.discard(pin)

    if frozenset(COMBO_CURRENT_KEYS) in KEY_COMBOS:
        # If the current set of keys are in the mapping, execute the function
        if KEY_COMBOS[frozenset(COMBO_CURRENT_KEYS)] == LAST_TRIGGERED_COMBO:
            device.emit(KEY_COMBOS[frozenset(COMBO_CURRENT_KEYS)], 2)
        else:
            device.emit(KEY_COMBOS[frozenset(COMBO_CURRENT_KEYS)], 1)
        LAST_TRIGGERED_COMBO = KEY_COMBOS[frozenset(COMBO_CURRENT_KEYS)]
    else:
        if LAST_TRIGGERED_COMBO is not None:
            device.emit(LAST_TRIGGERED_COMBO, 0)
            LAST_TRIGGERED_COMBO = None

    if pin == SHOW_OSD_KEY:
        if state == 1:
            showOverlay = True
            try:
                info = showOverlay
                overrideCounter.set()
            except Exception:
                pass
        else:
            showOverlay = False
            try:
                info = showOverlay
                overrideCounter.set()
            except Exception:
                pass

    if not hotkeyAction(pin):
        key = KEYS[pin]
        if PREVIOUS_KEYSTATES[pin] == 1 and state == 1:
            device.emit(key, 2)
        else:
            device.emit(key, state)
        PREVIOUS_KEYSTATES.update({pin: state})
        time.sleep(BOUNCE_TIME)
        logging.debug("Pin: {}, KeyCode: {}, Event: {}".format(pin, key, 'press' if state else 'release'))
    else:
        checkKeyInputPowerSaving()

    device.syn()
    PREVIOUS_KEYSTATES.update({pin: state})


def handle_shutdown(pin):
    state = 0 if gpio.input(pin) else 1
    if (state):
        logging.info("SHUTDOWN")
        doShutdown()


# Initialise Safe shutdown
if not SHUTDOWN == -1:
    gpio.add_event_detect(SHUTDOWN, gpio.BOTH, callback=handle_shutdown, bouncetime=1)

if not SENSOR_DETECT == -1:
    gpio.add_event_detect(SENSOR_DETECT, gpio.BOTH, callback=handle_sensor, bouncetime=1)

if keysConfig.has_option("HOTKEYS", "QUICKSAVE"):
    gpio.add_event_detect(QUICKSAVE, gpio.BOTH, callback=handle_quicksave, bouncetime=1)

# Initialise Buttons
for button in BUTTONS:
    gpio.add_event_detect(button, gpio.BOTH, callback=handle_button, bouncetime=1)

for key, pin in keysConfig.items('HOTKEYS'):
    HOTKEYS.append(int(pin))

    if not int(pin) in BUTTONS and int(pin) != QUICKSAVE:
        if pin != -1:
            gpio.setup(int(pin), gpio.IN, pull_up_down=gpio.PUD_UP)
            gpio.add_event_detect(int(pin), gpio.BOTH, callback=handle_button, bouncetime=1)

# Send centering commands
device.emit(uinput.ABS_X, int(VREF / 2), syn=False);
device.emit(uinput.ABS_Y, int(VREF / 2));

# Set up OSD service
try:
    mode = "nojoystick" if JOYSTICK_ENABLED == 'False' else "full"
    osd_proc = Popen([osd_path, bin_dir, mode], stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True)

    osd_in = osd_proc.stdin

    def _monitor_osd():
        ret = osd_proc.wait()
        logging.error(f"ERROR: OSD binary died with return code [{ret}]")
        sys.exit(1)

    monitor = thread.start_new_thread(_monitor_osd, ())

    time.sleep(1)
    if osd_proc.poll() is not None:
        logging.error(f"ERROR: Failed to start OSD, got return code [{osd_proc.poll()}]")
        os.kill(os.getpid(), signal.SIGINT)

except Exception:
    logging.exception("ERROR: Failed start OSD binary")
    sys.exit(1)


# Check for shutdown state
def checkShdn(volt):
    global lowbattery
    global info
    if volt < batt_shdn:
        lowbattery = 1
        info = 1
        overrideCounter.set()
        doShutdown()


# Read voltage
def readVoltage():
    global last_bat_read;
    voltVal = adc.read_adc(0, gain=1)
    print(voltVal)
    print('read')
    volt = int((float(voltVal) * (4.09 / 2047.0)) * 100)

    if volt < 300 or (last_bat_read > 300 and last_bat_read - volt > 6 and not last_bat_read == 450):
        volt = last_bat_read;

    last_bat_read = volt;

    return volt


# Get voltage percent
def getVoltagepercent(volt):
    return clamp(int(float(volt - batt_shdn) / float(batt_full - batt_shdn) * 100), 0, 100)


def readVolumeLevel():
    process = os.popen("amixer get Master | grep 'Left:' | awk -F'[][]' '{ print $2 }'")
    res = process.readline()
    process.close()

    vol = 0;
    try:
        vol = int(res.replace("%", "").replace("'C\n", ""))
    except Exception as e:
        logging.info("Audio Err    : " + str(e))

    return vol;


# Read wifi (Credits: kite's SAIO project) Modified to only read, not set wifi.
def readModeWifi(toggle=False):
    ret = 0;
    wifiVal = not os.path.exists(osd_path + 'wifi')  # int(ser.readline().rstrip('\r\n'))
    if toggle:
        wifiVal = not wifiVal
    global wifi_state
    if (wifiVal):
        if os.path.exists(osd_path + 'wifi'):
            os.remove(osd_path + 'wifi')
        if (wifi_state != 'ON'):
            wifi_state = 'ON'
            logging.info("Wifi    [ENABLING]")
            try:
                out = check_output(['sudo', rfkill_path, 'unblock', 'wifi'])
                logging.info("Wifi    [" + str(out) + "]")
            except Exception as e:
                logging.info("Wifi    : " + str(e))
                ret = wifi_warning  # Get signal strength

    else:
        with open(osd_path + 'wifi', 'a'):
            n = 1
        if (wifi_state != 'OFF'):
            wifi_state = 'OFF'
            logging.info("Wifi    [DISABLING]")
            try:
                out = check_output(['sudo', rfkill_path, 'block', 'wifi'])
                logging.info("Wifi    [" + str(out) + "]")
            except Exception as e:
                logging.info("Wifi    : " + str(e))
                ret = wifi_error
        return ret
    # check signal
    raw = check_output(['cat', '/proc/net/wireless'])
    strengthObj = re.search(r'.wlan0: \d*\s*(\d*)\.\s*[-]?(\d*)\.', raw.decode(), re.I)
    if strengthObj:
        strength = 0
        if (int(strengthObj.group(1)) > 0):
            strength = int(strengthObj.group(1))
        elif (int(strengthObj.group(2)) > 0):
            strength = int(strengthObj.group(2))
        logging.info("Wifi    [" + str(strength) + "]strength")
        if (strength > 55):
            ret = wifi_3bar
        elif (strength > 40):
            ret = wifi_2bar
        elif (strength > 5):
            ret = wifi_1bar
        else:
            ret = wifi_warning
    else:
        logging.info("Wifi    [---]strength")
        ret = wifi_error
    return ret


def readModeBluetooth(toggle=False):
    ret = 0;
    BtVal = not os.path.exists(osd_path + 'bluetooth')  # int(ser.readline().rstrip('\r\n'))
    if toggle:
        BtVal = not BtVal
    global bt_state
    if (BtVal):
        if os.path.exists(osd_path + 'bluetooth'):
            os.remove(osd_path + 'bluetooth')
        if (bt_state != 'ON'):
            bt_state = 'ON'
            logging.info("BT    [ENABLING]")
            try:
                out = check_output(['sudo', rfkill_path, 'unblock', 'bluetooth'])
                logging.info("BT      [" + str(out) + "]")
            except Exception as e:
                logging.info("BT    : " + str(e))
                ret = wifi_warning  # Get signal strength

    else:
        with open(osd_path + 'bluetooth', 'a'):
            n = 1
        if (bt_state != 'OFF'):
            bt_state = 'OFF'
            logging.info("BT    [DISABLING]")
            try:
                out = check_output(['sudo', rfkill_path, 'block', 'bluetooth'])
                logging.info("BT      [" + str(out) + "]")
            except Exception as e:
                logging.info("BT    : " + str(e))
                ret = wifi_error
        return ret
    # check if it's enabled
    raw = check_output(['hcitool', 'dev'])
    return True if raw.decode().find("hci0") > -1 else False


# Do a shutdown
def doShutdown(channel=None):
    # check_call("sudo killall emulationstation", shell=True)
    # time.sleep(1)
    check_call("sudo shutdown -h now", shell=True)
    try:
        sys.stdout.close()
    except:
        pass
    try:
        sys.stderr.close()
    except:
        pass
    sys.exit(0)


# Signals the OSD binary
def updateOSD(volt=0, bat=0, temp=0, wifi=0, audio=0, lowbattery=0, info=False, charge=False, bluetooth=False):
    global showOverlay
    showState = showOverlay if SHOW_OVERLAY_HOTKEY_ONLY else True
    commands = "s" + str(int(showState)) + " p" + str(int((backlightSetting / 1024) * 100)) + " v" + str(
        volt) + " b" + str(bat) + " t" + str(temp) + " w" + str(
        wifi) + " a" + str(
        audio) + " j" + ("1 " if joystick else "0 ") + " u" + ("1 " if bluetooth else "0 ") + " l" + (
                   "1 " if lowbattery else "0 ") + " " + ("on " if info else "off ") + (
                   "charge" if charge else "ncharge") + "\n"
    # print commands
    osd_proc.send_signal(signal.SIGUSR1)
    osd_in.write(commands)
    osd_in.flush()


# Misc functions
def clamp(n, minn, maxn):
    return max(min(maxn, n), minn)


def volumeUp():
    global volume
    volume = min(100, volume + 5)
    os.system("amixer sset -q 'PCM' " + str(volume) + "%")


def volumeDown():
    global volume
    volume = max(0, volume - 5)
    os.system("amixer sset -q 'PCM' " + str(volume) + "%")


def inputReading():
    global volume
    global wifi
    global info
    global volt
    global bat
    global charge
    global joystick
    while (1):
        if joystick == True:
            checkJoystickInput()
        time.sleep(.05)


def checkKeyInputPowerSaving():
    global info
    global wifi
    global joystick
    global bluetooth
    global bat
    global volume
    global volt
    global showOverlay

    info = showOverlay
    overrideCounter.set()

    if not gpio.input(SHOW_OSD_KEY):
        if not gpio.input(VOLUME_UP):
            volumeUp()
            time.sleep(0.6)
        elif not gpio.input(VOLUME_DOWN):
            volumeDown()
            time.sleep(0.6)
        elif not gpio.input(TOGGLE_WIFI):
            wifi = readModeWifi(True)
            time.sleep(0.6)
        elif not gpio.input(TOGGLE_JOYSTICK):
            joystick = not joystick
            time.sleep(0.6)
        elif not gpio.input(TOGGLE_BLE):
            bluetooth = readModeBluetooth(True)
            time.sleep(0.6)
        elif not gpio.input(BRIGHTNESS_UP):
            brightnessUp()
            time.sleep(0.6)
        elif not gpio.input(BRIGHTNESS_DOWN):
            brightnessDown()
            time.sleep(0.6)
        elif SAFE_SHUTDOWN != -1:
            if not gpio.input(SAFE_SHUTDOWN):
                doShutdown()


def checkJoystickInput():
    an1 = adc.read_adc(2, gain=2 / 3);
    an0 = adc.read_adc(1, gain=2 / 3);

    logging.debug("X: {} | Y: {}".format(an0, an1))
    logging.debug("Above: {} | Below: {}".format((VREF / 2 + DZONE), (VREF / 2 - DZONE)))

    # Check and apply joystick states
    if (an0 > ((VREF / 2 + DZONE)) or (an0 < (VREF / 2 - DZONE))) and an0 <= VREF:
        val = an0 - 100 - 200 * (an0 < VREF / 2 - DZONE) + 200 * (an0 > VREF / 2 + DZONE)
        device.emit(uinput.ABS_X, val, syn=False)
    else:
        # Center the sticks if within deadzone
        device.emit(uinput.ABS_X, VREF / 2, syn=False)
    if ((an1 > (VREF / 2 + DZONE)) or (an1 < (VREF / 2 - DZONE))) and an1 <= VREF:
        valy = an1 + 100 - 200 * (an1 < VREF / 2 - DZONE) + 200 * (an1 > VREF / 2 + DZONE)
        device.emit(uinput.ABS_Y, valy)
    else:
        # Center the sticks if within deadzone
        device.emit(uinput.ABS_Y, VREF / 2)


def constrain(val, min_val, max_val):
    return min(max_val, max(min_val, val))


def brightnessUp():
    global backlightSetting
    backlightSetting = constrain(backlightSetting + 128, 0, 1024)
    wiringpi.pwmWrite(13, backlightSetting);


def brightnessDown():
    global backlightSetting
    backlightSetting = constrain(backlightSetting - 128, 0, 1024)
    wiringpi.pwmWrite(13, backlightSetting);


def exit_gracefully(signum=None, frame=None):
    gpio.cleanup
    osd_proc.terminate()
    sys.exit(0)


signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

# Read Initial States
volume = readVolumeLevel()

wifi = readModeWifi()
bluetooth = bluetooth = readModeBluetooth()

if JOYSTICK_ENABLED == 'True':
    inputReadingThread = thread.start_new_thread(inputReading, ())

try:
    while 1:
        try:
            if not adc == False:
                volt = readVoltage()
                print(f"Voltage: {volt}")
                bat = getVoltagepercent(volt)
                print(f"Battery: {bat}%")
            checkShdn(volt)
            updateOSD(volt, bat, 20, wifi, volume, lowbattery, info, charge, bluetooth)
            print('update OSD')
            overrideCounter.wait(10)
            if overrideCounter.is_set():
                overrideCounter.clear()
            runCounter = 0

        except Exception:
            logging.info("EXCEPTION")
            pass

except KeyboardInterrupt:
    exit_gracefully()
