@echo off

:: Create Conda environment
echo "Creating Conda environment with Python 3.10..."
conda create -p .\.conda python=3.10 -y
IF %ERRORLEVEL% NEQ 0 (
    echo "Failed to create Conda environment."
    exit /b %ERRORLEVEL%
)

:: Activate Conda environment and install patchright
echo "Activating Conda environment and installing patchright..."
conda activate .\.conda
IF %ERRORLEVEL% NEQ 0 (
    echo "Failed to activate Conda environment."
    exit /b %ERRORLEVEL%
)

.conda\Scripts\pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    echo "Failed to install Python dependencies."
    exit /b %ERRORLEVEL%
)

:: Install Chromium driver for Patchright
echo "Installing Chromium driver for Patchright..."
.\.conda\Scripts\python -m patchright install chromium
IF %ERRORLEVEL% NEQ 0 (
    echo "Failed to install Chromium driver."
    exit /b %ERRORLEVEL%
)

echo "Installation complete. To run the script, activate the environment and execute main.py:"
echo ".conda\Scripts\python main.py"
