#!/usr/bin/env bash
#
# Atualiza a tag da imagem no manifesto GitOps.
# Uso: ./update-image-tag.sh <service> <image-tag>
#   <service>   nome do microsservico (ex: auth-service)
#   <image-tag> nova tag (ex: 3f9a1b2c3d4e)
#
# Esse script e chamado pelo pipeline de CI ao final do fluxo,
# simulando o "pull request" do GitOps para o ArgoCD detectar.

set -euo pipefail

GITOPS_DIR="$(dirname "$0")/../gitops"
SERVICE="${1:?Uso: update-image-tag.sh <service> <image-tag>}"
IMAGE_TAG="${2:?Uso: update-image-tag.sh <service> <image-tag>}"
MANIFEST="${GITOPS_DIR}/${SERVICE}/base.yaml"
REGISTRY="${ECR_REGISTRY:-000000000000.dkr.ecr.us-east-1.amazonaws.com}"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "ERRO: manifesto nao encontrado: ${MANIFEST}" >&2
  exit 1
fi

NEW_IMAGE="${REGISTRY}/togglemaster/${SERVICE}:${IMAGE_TAG}"

sed -i "s|image: .*${SERVICE}:.*|image: ${NEW_IMAGE}|" "${MANIFEST}"

echo "==> Tag atualizada em ${MANIFEST}"
grep -n "image:" "${MANIFEST}"