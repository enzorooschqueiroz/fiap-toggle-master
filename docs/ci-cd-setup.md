# Configuração CI/CD - GitHub Secrets

Para os workflows do GitHub Actions funcionarem, configure os seguintes secrets
em `Settings > Secrets and variables > Actions` do repositório.

## Secrets obrigatórios

| Secret | Descrição |
|--------|-----------|
| `AWS_ACCESS_KEY_ID` | Access Key da conta AWS (recomendado criar usuário IAM dedicado) |
| `AWS_SECRET_ACCESS_KEY` | Secret Key correspondente |
| `AWS_ROLE_TO_ASSUME` | (Alternativa OIDC) ARN da role para assume-role |
| `ECR_REGISTRY` | Registry do ECR (ex: `123456789012.dkr.ecr.us-east-1.amazonaws.com`) |
| `GITOPS_TOKEN` | GitHub PAT para push automático no repo GitOps |
| `AUTH_DB_PASSWORD` | Senha do RDS auth |
| `FLAGS_DB_PASSWORD` | Senha do RDS flags |
| `TARGETING_DB_PASSWORD` | Senha do RDS targeting |

## Variáveis (Settings > Variables)

| Variable | Descrição |
|----------|-----------|
| `GITOPS_REPO` | Nome do repo GitOps (se separado do monorepo) |

---

## IAM User para o Pipeline (conta pessoal)

Crie um usuário IAM `github-actions` com policy inline:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:GetRepositoryPolicy",
        "ecr:DescribeRepositories",
        "ecr:ListImages",
        "ecr:PutImage",
        "ecr:UploadLayerPart",
        "ecr:BatchGetImage",
        "ecr:CompleteLayerUpload",
        "ecr:InitiateLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:*",
        "dynamodb:*"
      ],
      "Resource": "*"
    }
  ]
}
```

Alternativa mais simples para prosseguir rápido: usar `AdministratorAccess` no
usuário do GitHub Actions durante o desenvolvimento (não recomendado em produção).