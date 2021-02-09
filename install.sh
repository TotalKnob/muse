#!/bin/bash

sudo apt update && sudo apt install -y python curl

# Update pip to v20
curl https://bootstrap.pypa.io/2.7/get-pip.py | python -

# Install requirements
sudo apt install -y \
	vim git htop virtualenv fish clang wget build-essential \
	autoconf python-dev cmake sudo \
	python-tk python-numpy python-psutil python-virtualenv python-pandas \
	python-matplotlib python-seaborn python-termcolor
pip install wllvm
pip install -U scikit-learn

./prepareEnvironment.sh

# Build and install muse, AFL and QSYM
./set.sh

./Docker/docker_build_muse.sh

