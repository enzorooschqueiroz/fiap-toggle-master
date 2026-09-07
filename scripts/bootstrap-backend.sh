#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
STATE_BUCKET="${1:-togglemaster-tfstate-185796529499}"
LOCK_TABLE="${2:-terraform-lock}"

echo "==> Bootstrapping Terraform remote state (bucket + lock table)..."
echo "    Region : ${AWS_REGION}"
echo "    Bucket : ${STATE_BUCKET}"
echo "    Table  : ${LOCK_TABLE}"

# 1. S3 bucket for the tfstate
if aws s3api head-bucket --bucket "${STATE_BUCKET}" --region "${AWS_REGION}" 2>/dev/null; then
  echo "    Bucket '${STATE_BUCKET}' already exists, skipping."
else
  aws s3api create-bucket \
    --bucket "${STATE_BUCKET}" \
    --region "${AWS_REGION}"
  aws s3api put-bucket-versioning \
    --bucket "${STATE_BUCKET}" \
    --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption \
    --bucket "${STATE_BUCKET}" \
    --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws s3api put-bucket-tagging \
    --bucket "${STATE_BUCKET}" \
    --tagging 'TagSet=[{Key=Project,Value=ToggleMaster},{Key=Purpose,Value=TerraformState}]'
  echo "    Bucket created and configured."
fi

# 2. DynamoDB table for state locking
if aws dynamodb describe-table --table-name "${LOCK_TABLE}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  echo "    Lock table '${LOCK_TABLE}' already exists, skipping."
else
  aws dynamodb create-table \
    --table-name "${LOCK_TABLE}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "${AWS_REGION}"
  echo "    Lock table created."
fi

echo "==> Done. Seu backend remoto está pronto."