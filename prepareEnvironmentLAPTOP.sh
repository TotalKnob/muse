#!/bin/bash

# AFL specific requirements
echo core | sudo tee /proc/sys/kernel/core_pattern
# Governor presumably only required on laptops
cd /sys/devices/system/cpu && echo performance | sudo tee cpu*/cpufreq/scaling_governor

