#!/bin/bash
set -e

echo "Deploying Smart Hospital Management System..."

source .venv/bin/activate

# Deploy infrastructure
sam build
sam deploy --guided

echo "Deployment complete!"
