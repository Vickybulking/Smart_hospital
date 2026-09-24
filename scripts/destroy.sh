#!/bin/bash
set -e

echo "Destroying Smart Hospital Management System deployment..."

source .venv/bin/activate

# Destroy infrastructure
sam delete --stack-name smart-hospital-management --region us-east-1

echo "Destruction complete!"
