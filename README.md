<div align="center">
  <h1>ToggleMaster</h1>
  <p><strong>Feature Flag Management Platform</strong></p>
  <p>FIAP Tech Challenge - Fase 2 & 3</p>
  <br>
</div>

## Architecture

ToggleMaster is a microservices ecosystem for managing feature flags at scale. Five specialized services work together to provide flag definition, targeting rules, high-performance evaluation, and analytics.

```
                    ┌─────────────┐
                    │   Client    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Ingress   │
                    │  (NGINX)    │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
 ┌──────▼──────┐   ┌──────▼──────┐   ┌───────▼──────┐
 │ auth-service │   │flag-service │   │targeting-svc │
 │  (Go) 8001   │   │(Py) 8002    │   │(Py) 8003     │
 │ PostgreSQL   │   │PostgreSQL   │   │PostgreSQL    │
 └──────────────┘   └─────────────┘   └──────────────┘
                                    │
                           ┌───────▼──────┐
                           │evaluation-svc│
                           │  (Go) 8004   │
                           │    Redis     │
                           └───────┬──────┘
                                   │ SQS
                           ┌───────▼──────┐
                           │analytics-svc │
                           │  (Py) 8005   │
                           │  DynamoDB    │
                           └──────────────┘
```

## Services

| Service | Language | Port | Database | Purpose |
|---------|----------|------|----------|---------|
| **auth-service** | Go | 8001 | PostgreSQL | API key management and authentication |
| **flag-service** | Python/Flask | 8002 | PostgreSQL | CRUD for feature flag definitions |
| **targeting-service** | Python/Flask | 8003 | PostgreSQL | Percentage-based targeting rules |
| **evaluation-service** | Go | 8004 | Redis | High-performance flag evaluation (hot path) |
| **analytics-service** | Python/Flask | 8005 | DynamoDB / SQS | Async event consumer and analytics storage |

## Getting Started

### Local Development

Run the entire ecosystem locally with Docker Compose:

```bash
docker compose up --build
```

This starts all 9 containers (5 services + 4 databases):

| Container | Port |
|-----------|------|
| auth-service | 8001 |
| flag-service | 8002 |
| targeting-service | 8003 |
| evaluation-service | 8004 |
| analytics-service | 8005 |
| auth-db (PostgreSQL) | 5432 |
| flags-db (PostgreSQL) | 5433 |
| redis | 6379 |
| dynamodb-local | 8000 |

### Creating an API Key

```bash
curl -X POST http://localhost:8001/admin/keys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-master-key-change-in-production" \
  -d '{"name": "my-service"}'
```

### Creating a Feature Flag

```bash
curl -X POST http://localhost:8002/flags \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{"name": "enable-new-dashboard", "description": "New dashboard UI", "is_enabled": true}'
```

### Creating a Targeting Rule

```bash
curl -X POST http://localhost:8003/rules \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -d '{"flag_name": "enable-new-dashboard", "rules": {"type": "PERCENTAGE", "value": 50}}'
```

### Evaluating a Flag

```bash
curl "http://localhost:8004/evaluate?user_id=user-123&flag_name=enable-new-dashboard"
```

## Kubernetes Deployment

The `k8s/` directory contains manifests for deploying on AWS EKS:

```bash
kubectl apply -f k8s/00-namespaces.yaml
kubectl apply -f k8s/auth-service/
kubectl apply -f k8s/flag-service/
kubectl apply -f k8s/targeting-service/
kubectl apply -f k8s/evaluation-service/
kubectl apply -f k8s/analytics-service/
kubectl apply -f k8s/ingress.yaml
```

### Prerequisites

- AWS EKS cluster
- 3 RDS PostgreSQL instances (one per relational service)
- ElastiCache Redis cluster
- DynamoDB table (`ToggleMasterAnalytics`)
- SQS queue (`toggle-events-queue`)
- ECR repositories for container images
- Metrics Server
- NGINX Ingress Controller

## Project Structure

```
├── db/                        # Database initialization scripts
│   ├── auth/                  # auth-service schema
│   └── flags/                 # flags + targeting schema
├── docker-compose.yml         # Local development environment
├── docs/                      # API collections (Postman, Insomnia) + setup guides
├── k8s/                       # Kubernetes manifests (legado fase 2)
├── gitops/                    # [FASE 3] Manifests GitOps monitorados pelo ArgoCD
│   ├── argocd/application.yaml
│   ├── auth-service/base.yaml
│   ├── flag-service/base.yaml
│   ├── targeting-service/base.yaml
│   ├── evaluation-service/base.yaml
│   ├── analytics-service/base.yaml
│   └── ingress.yaml
├── terraform/                 # [FASE 3] IaC (AWS)
│   ├── backend.tf
│   ├── main.tf
│   ├── outputs.tf
│   ├── versions.tf
│   └── modules/
│       ├── networking/
│       ├── eks/
│       ├── rds/
│       ├── elasticache/
│       ├── dynamodb/
│       ├── sqs/
│       └── ecr/
├── .github/workflows/         # [FASE 3] CI/CD + DevSecOps
│   ├── ci-go.yml              # auth + evaluation (Go)
│   ├── ci-python.yml          # flag + targeting + analytics (Python)
│   └── terraform.yml          # Plan/Apply da infra
├── scripts/                   # Scripts auxiliares
│   ├── bootstrap-backend.sh   # Cria bucket S3 + tabela de lock
│   ├── set-account-id.sh      # Corrige Account ID nos manifests
│   └── update-image-tag.sh    # Atualiza tag no GitOps
└── services/                  # Microservices source code
    ├── auth-service/          # Go - Authentication
    ├── flag-service/          # Python - Flag CRUD
    ├── targeting-service/     # Python - Targeting rules
    ├── evaluation-service/    # Go - Evaluation engine
    └── analytics-service/     # Python - Analytics consumer
```

---

## Fase 3 - IaC, CI/CD e GitOps

"Se não está no código, não existe."

### 1. Infraestrutura (Terraform)

```bash
# 1. Crie o backend remoto (S3 + DynamoDB lock)
./scripts/bootstrap-backend.sh

# 2. Configure as senhas
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# edite as senhas do RDS

# 2. Corrija o Account ID nos manifests (conta pessoal AWS)
./scripts/set-account-id.sh <SEU_ACCOUNT_ID>

# 3. Provisione
cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

> **Nota:** Conta pessoal AWS, portanto as roles IAM são criadas via Terraform.
> Se usar AWS Academy, remova as roles e associe a LabRole (veja `docs/`).

### 2. Pipeline DevSecOps (GitHub Actions)

Cada serviço tem pipeline com: **Build & Test → Lint → SCA (Trivy) → SAST (gosec/bandit) → Container Scan (Trivy image) → Push ECR**.

Regra de bloqueio: vulnerabilidade **CRÍTICA** falha o pipeline.

Configure os secrets em `docs/ci-cd-setup.md`.

### 3. GitOps (ArgoCD)

```bash
# Instale o ArgoCD e configure seguindo:
less docs/argocd-setup.md
```

Fluxo: CI faz push da imagem no ECR → CI atualiza a tag em `gitops/<service>/base.yaml` → ArgoCD detecta e sincroniza no cluster.

## Tech Stack

- **Languages:** Go 1.21, Python 3.9
- **Framework:** Flask (Python services)
- **Databases:** PostgreSQL 15, Redis 7, DynamoDB
- **Messaging:** AWS SQS
- **Orchestration:** Kubernetes (EKS)
- **Containers:** Docker, Amazon ECR
- **IaC:** Terraform (VPC, EKS, RDS, ElastiCache, DynamoDB, SQS, ECR)
- **CI/CD:** GitHub Actions (DevSecOps)
- **GitOps:** ArgoCD


<div align="center">
  <p><strong>FIAP - Tech Challenge Fase 3</strong></p>
</div>
