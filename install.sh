#!/bin/bash

# Create Conda environment
echo "Creating Conda environment with Python 3.10..."
conda create -p ./.conda python=3.10 -y || { echo "Failed to create Conda environment."; exit 1; }

# Activate Conda environment and install patchright
echo "Activating Conda environment and installing patchright..."
./.conda/bin/pip install -r requirements.txt || { echo "Failed to install Python dependencies."; exit 1; }

# Install Chromium driver for Patchright
echo "Installing Chromium driver for Patchright..."
./.conda/bin/python -m patchright install chromium || { echo "Failed to install Chromium driver."; exit 1; }

echo "Installation complete. To run the script, activate the environment and execute main.py:"
echo "./.conda/bin/python main.py"
