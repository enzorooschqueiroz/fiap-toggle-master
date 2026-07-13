<div align="center">
  <h1>ToggleMaster</h1>
  <p><strong>Feature Flag Management Platform</strong></p>
  <p>FIAP Tech Challenge - Fase 2</p>
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
├── docs/                      # API collections (Postman, Insomnia)
├── k8s/                       # Kubernetes manifests
│   ├── 00-namespaces.yaml     
│   ├── ingress.yaml           
│   ├── auth-service/          
│   ├── flag-service/          
│   ├── targeting-service/     
│   ├── evaluation-service/    
│   └── analytics-service/     
└── services/                  # Microservices source code
    ├── auth-service/          # Go - Authentication
    ├── flag-service/          # Python - Flag CRUD
    ├── targeting-service/     # Python - Targeting rules
    ├── evaluation-service/    # Go - Evaluation engine
    └── analytics-service/     # Python - Analytics consumer
```

## Tech Stack

- **Languages:** Go 1.21, Python 3.9
- **Framework:** Flask (Python services)
- **Databases:** PostgreSQL 15, Redis 7, DynamoDB
- **Messaging:** AWS SQS
- **Orchestration:** Kubernetes (EKS)
- **Containers:** Docker, Amazon ECR


<div align="center">
  <p><strong>FIAP - Tech Challenge Fase 2</strong></p>
</div>
