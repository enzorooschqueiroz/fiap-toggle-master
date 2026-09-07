#!/usr/bin/env bash
#
# Substitui o Account ID placeholder (000000000000) nos manifests GitOps/K8s
# pelo Account ID real da conta AWS.
# Uso: ./set-account-id.sh 123456789012

set -euo pipefail

ACCOUNT_ID="${1:?Uso: set-account-id.sh <account-id>}"

# Valida se é um número de 12 dígitos
if ! [[ "${ACCOUNT_ID}" =~ ^[0-9]{12}$ ]]; then
  echo "ERRO: Account ID invalido. Deve conter exatamente 12 digitos." >&2
  exit 1
fi

echo "==> Atualizando manifests (placeholder 000000000000 -> ${ACCOUNT_ID})..."

grep -rl "000000000000" gitops/ k8s/ 2>/dev/null | while read -r file; do
  sed -i "s|000000000000|${ACCOUNT_ID}|g" "${file}"
  echo "  OK  ${file}"
done

echo "==> Concluido."