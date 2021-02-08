#!/bin/bash

sudo apt update && sudo apt install python

# Update pip to v20
curl https://bootstrap.pypa.io/2.7/get-pip.py | python -

# Install requirements
sudo apt install \
	vim git htop virtualenv fish clang wget build-essential \
	autoconf python-dev cmake sudo curl \
	python-tk python-numpy python-psutil python-virtualenv python-pandas \
	python-scikit-learn python-matplotlib python-seaborn python-termcolor
pip install wllvm


# Build and install muse, AFL and QSYM
./set.sh

./Docker/docker_build_muse.sh

# AFL specific requirements
echo core | sudo tee /proc/sys/kernel/core_pattern
# Governor presumably only required on laptops
cd /sys/devices/system/cpu && echo performance | sudo tee cpu*/cpufreq/scaling_governor

