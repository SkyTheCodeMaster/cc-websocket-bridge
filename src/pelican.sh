#!/bin/bash

# Config file for Pelican Egg
# Python interpreter
PYTHON="python3.11"
MAIN_FILE="main.py"

# Upgrade pip
$PYTHON -m pip install -U pip

# Install dependencies
$PYTHON -m pip install -r requirements.txt

# Generate run.sh
cat <<END > run.sh
#!/bin/bash

$PYTHON $MAIN_FILE
END

# Make run.sh executable
chmod +x run.sh