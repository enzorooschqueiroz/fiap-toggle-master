#!/usr/bin/env bash
# Cria os Secrets dos 5 serviços a partir do `terraform output` + terraform.tfvars
# e aplica os schemas (db/*.sql) nos RDS via um pod psql efêmero dentro do cluster.
# Uso: AWS_PROFILE=pessoal ./scripts/create-service-secrets.sh [.env.observability]
#   SERVICE_API_KEY (opcional, no ambiente) -> chave usada pelo evaluation-service;
#   se vazia, gere com scripts/bootstrap-api-key.sh depois que o auth-service subir.
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env.observability}"
[[ -f "$ENV_FILE" ]] || { echo "Arquivo $ENV_FILE não encontrado"; exit 1; }
MASTER_KEY=$(grep -E '^MASTER_KEY=' "$ENV_FILE" | cut -d= -f2-)
[[ -n "$MASTER_KEY" ]] || { echo "MASTER_KEY vazia em $ENV_FILE"; exit 1; }

tfout() { terraform -chdir=terraform output -raw "$1"; }
tfvar() { grep -E "^$1[[:space:]]*=" terraform/terraform.tfvars | sed -E 's/^[^=]+=[[:space:]]*"?([^"]*)"?[[:space:]]*$/\1/'; }
urlenc() { python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }

AUTH_HOST=$(tfout rds_auth_endpoint);   AUTH_PW=$(urlenc "$(tfvar auth_db_password)")
FLAGS_HOST=$(tfout rds_flags_endpoint); FLAGS_PW=$(urlenc "$(tfvar flags_db_password)")
TGT_HOST=$(tfout rds_targeting_endpoint); TGT_PW=$(urlenc "$(tfvar targeting_db_password)")
REDIS_HOST=$(tfout redis_endpoint)

AUTH_URL="postgres://toggle_user:${AUTH_PW}@${AUTH_HOST}/auth?sslmode=require"
FLAGS_URL="postgres://toggle_user:${FLAGS_PW}@${FLAGS_HOST}/flags?sslmode=require"
TGT_URL="postgres://toggle_user:${TGT_PW}@${TGT_HOST}/targeting?sslmode=require"

for ns in auth flag targeting evaluation analytics; do
  kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
done
apply_secret() { kubectl create secret generic "$@" --dry-run=client -o yaml | kubectl apply -f - >/dev/null; }

apply_secret auth-service-secret -n auth --from-literal=DATABASE_URL="$AUTH_URL" --from-literal=MASTER_KEY="$MASTER_KEY"
apply_secret flag-service-secret -n flag --from-literal=DATABASE_URL="$FLAGS_URL" --from-literal=MASTER_KEY="$MASTER_KEY"
apply_secret targeting-service-secret -n targeting --from-literal=DATABASE_URL="$TGT_URL"
apply_secret evaluation-service-secret -n evaluation \
  --from-literal=REDIS_URL="redis://${REDIS_HOST}:6379/0" \
  --from-literal=SERVICE_API_KEY="${SERVICE_API_KEY:-pendente}"
# analytics usa a role IAM do nó (SQS/DynamoDB) — sem access keys
apply_secret analytics-service-secret -n analytics --from-literal=PLACEHOLDER=unused
echo "Secrets dos serviços aplicados."

# Schemas: idempotentes (CREATE TABLE IF NOT EXISTS)
run_sql() {  # $1=nome $2=url $3..=arquivos sql
  local name=$1 url=$2; shift 2
  kubectl delete pod "db-init-$name" -n default --ignore-not-found >/dev/null
  # shellcheck disable=SC2016  # $DATABASE_URL expande dentro do pod
  cat "$@" | kubectl run "db-init-$name" -n default -i --rm --restart=Never --quiet \
    --image=postgres:17-alpine --env="DATABASE_URL=$url" \
    --command -- sh -c 'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q' \
    && echo "Schema aplicado: $name"
}
run_sql auth "$AUTH_URL" db/auth/init.sql
run_sql flags "$FLAGS_URL" db/flags/01-flags.sql
run_sql targeting "$TGT_URL" db/flags/02-targeting.sql
