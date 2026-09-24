#!/bin/bash
set -e

echo "Setting up Smart Hospital Management System..."

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure AWS CLI
aws configure

# Deploy infrastructure
sam build
sam deploy --guided

echo "Setup complete!"
