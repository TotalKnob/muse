#!/bin/bash

./set.sh

./Docker/docker_build_muse.sh

echo core | sudo tee /proc/sys/kernel/core_pattern

cd /sys/devices/system/cpu && echo performance | sudo tee cpu*/cpufreq/scaling_governor

