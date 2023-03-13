# Setup the virtual environment
echo "Initializing venv"
python3.11 -m venv .

# Activate it
echo "Activating..."
source bin/activate

echo "Installing requirements"
pip install -r requirements.txt

echo "All done. Exiting."
deactivate