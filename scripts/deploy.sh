#!/usr/bin/env bash
# Build and deploy Carely to AWS, then wire the frontend config and seed demo data.
# Usage: scripts/deploy.sh [stack-name] [region] [environment]
#   defaults: carely-dev  ap-south-1  development
set -euo pipefail

STACK="${1:-carely-dev}"
REGION="${2:-ap-south-1}"
ENV="${3:-development}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Building SAM application"
sam build --template "$ROOT/infrastructure/template.yaml" --region "$REGION"

echo "==> Deploying stack $STACK to $REGION"
sam deploy \
  --template "$ROOT/.aws-sam/build/template.yaml" \
  --stack-name "$STACK" \
  --region "$REGION" \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --no-confirm-changeset \
  --no-disable-rollback \
  --parameter-overrides "EnvironmentName=$ENV"

echo "==> Writing frontend/config.js from stack outputs"
"$ROOT/scripts/update_frontend_config.sh" "$STACK"

echo "==> Seeding demo data"
python3 "$ROOT/scripts/seed_data.py" --stack "$STACK"

echo
echo "Deployment complete. Serve the frontend with:"
echo "  python3 -m http.server 8080 --directory frontend"
echo "then open http://localhost:8080 (demo credentials printed above)."
