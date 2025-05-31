#!/bin/bash

# Service file details
DESCRIPTION="Generic multi-node websocket relay"
SERVICE_NAME="wsrelay"

# Python interpreter
PYTHON="python3.13"
MAIN_FILE="main.py"
VENV_PATH="venv"

# Generate the venv
$PYTHON -m venv $VENV_PATH
if [ $? -ne 0 ]; then
  echo "Failed to build venv!"
fi

# Switch to the venv
source $VENV_PATH/bin/activate

# Upgrade pip
$PYTHON -m pip install -U pip

# Install dependencies
$PYTHON -m pip install -r requirements.txt

# Generate run.sh
cat <<END > run.sh
#!/bin/bash

source $VENV_PATH/bin/activate
$PYTHON $MAIN_FILE
END

# Make run.sh executable
chmod +x run.sh

# Generate the systemd service.
CURRENT_DIRECTORY=$(pwd)
CURRENT_USER=$(id -un)
EXEC_PATH="$CURRENT_DIRECTORY/run.sh"
SERVICE_FILE="$SERVICE_NAME.service"

cat <<END > $SERVICE_FILE
[Unit]
Description=$DESCRIPTION
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=3
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIRECTORY
ExecStart=/bin/bash $EXEC_PATH
StandardError=journal
StandardOutput=journal
StandardInput=null

[Install]
WantedBy=multi-user.target
END

echo "Add the service file to systemd:"
echo "sudo systemctl link $CURRENT_DIRECTORY/$SERVICE_FILE"
echo "sudo systemctl enable $SERVICE_NAME"
echo "sudo systemctl start $SERVICE_NAME"