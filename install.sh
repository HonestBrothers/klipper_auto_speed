#!/bin/bash
# automatically calculate your printer's maximum acceleration/velocity
#
# Copyright (C) 2024 Anonoei <dev@anonoei.com>
#
# This file may be distributed under the terms of the MIT license.

# Force script to exit if an error occurs
set -e

KLIPPER_PATH="${HOME}/klipper"
SYSTEMDDIR="/etc/systemd/system"
SRCDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )"/ && pwd )"

# Verify we're running as root
if [ "$(id -u)" -eq 0 ]; then
    echo "This script must not run as root"
    exit -1
fi

# Check if Klipper is installed
if [ "$(sudo systemctl list-units --full -all -t service --no-legend | grep -F "klipper.service")" ]; then
    echo "Klipper service found!"
else
    echo "Klipper service not found, please install Klipper first"
    exit -1
fi

# Check for old python
~/klippy-env/bin/python -c 'import sys; assert sys.version_info[0] == 3, "Python 3 is required."'

# Link auto speed to klipper
echo "Linking auto speed to Klipper..."
ln -sf "${SRCDIR}/auto_speed.py" "${KLIPPER_PATH}/klippy/extras/auto_speed.py"
mkdir -p "${KLIPPER_PATH}/klippy/extras/autospeed"
for file in `ls autospeed/*.py`; do
    ln -sf "${SRCDIR}/${file}" "${KLIPPER_PATH}/klippy/extras/${file}"
done

# Install matplotlib
echo "Installing matplotlib in klippy..."
~/klippy-env/bin/python -m pip install matplotlib

# Check to see if Gcode Shell Command is installed
cd ~
if test -f "~/klipper/klippy/extras/gcode_shell_command.py"; then
    echo "Gcode shell command found!"
else
    echo "Installing Gcode shell command..."
    cp ~/klipper_auto_speed/gcode_shell_command.py ~/klipper/klippy/extras/gcode_shell_command.py
fi

# Check to see if autoacc.cfg is installed
cd ~
if test -f "~/printer_data/config/autoacc.cfg"; then
    echo "autoacc.cfg found!"
    echo "If you're intending to reinstall autoacc.cfg, please remove the file from ~/printer_data/config/ and run this script again"
else
    echo "Moving autoacc.cfg to /home/pi/printer_data/config/"
    cp ~/klipper_auto_speed/autoacc.cfg ~/printer_data/config/autoacc.cfg
fi

# Restart klipper
echo "Restarting Klipper..."
sudo systemctl restart klipper