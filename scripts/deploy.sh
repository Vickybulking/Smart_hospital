#!/usr/bin/env bash
# Build and deploy Carely to AWS, then wire the frontend config and seed demo data.
# Usage: scripts/deploy.sh [stack-name] [region] [environment] [aws-profile]
#   defaults: carely-dev  ap-southeast-2  development  (profile: AWS_PROFILE or default)
set -euo pipefail

STACK="${1:-carely-dev}"
REGION="${2:-ap-southeast-2}"
ENV="${3:-development}"
PROFILE="${4:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Optional AWS profile for every aws/sam call in this script
if [ -n "$PROFILE" ]; then export AWS_PROFILE="$PROFILE"; fi

echo "==> Building SAM application"
sam build --template "$ROOT/infrastructure/template.yaml" --region "$REGION"

echo "==> Deploying stack $STACK to $REGION"
API_ID=$(sam deploy \
  --template "$ROOT/.aws-sam/build/template.yaml" \
  --stack-name "$STACK" \
  --region "$REGION" \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --no-confirm-changeset \
  --no-disable-rollback \
  --parameter-overrides "EnvironmentName=$ENV" \
  | tee /dev/stderr | grep -oP 'https://\K[a-z0-9]+(?=\.execute-api)' | head -1 || true)

echo "==> SAM quirk fix: CORS OPTIONS methods inherit the default Cognito authorizer;"
echo "    force authorizationType=NONE on every OPTIONS method and re-deploy the stage."
if [ -n "$API_ID" ]; then
  for RID in $(aws apigateway get-resources --rest-api-id "$API_ID" --region "$REGION" \
      --query "items[?resourceMethods && contains(keys(resourceMethods), 'OPTIONS')].id" --output text); do
    aws apigateway update-method --rest-api-id "$API_ID" --resource-id "$RID" --http-method OPTIONS \
      --region "$REGION" --patch-operations 'op=replace,path=/authorizationType,value=NONE' >/dev/null || true
  done
  aws apigateway create-deployment --rest-api-id "$API_ID" --stage-name "$ENV" --region "$REGION" >/dev/null
  echo "    patched OPTIONS methods and re-deployed stage $ENV"
else
  echo "    (could not detect API id — check OPTIONS authorizationType manually)"
fi

echo "==> Writing frontend/config.js from stack outputs"
"$ROOT/scripts/update_frontend_config.sh" "$STACK"

echo "==> Seeding demo data"
python3 "$ROOT/scripts/seed_data.py" --stack "$STACK"

echo
echo "Deployment complete. Serve the frontend with:"
echo "  python3 -m http.server 8080 --directory frontend"
echo "then open http://localhost:8080 (demo credentials printed above)."
