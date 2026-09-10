# Setup do ArgoCD no Cluster EKS

Este guia cobre a instalação do ArgoCD e a configuração para que ele monitore
a pasta `gitops/` do monorepo.

## Pré-requisitos
- Cluster EKS provisionado (via Terraform da fase 3)
- `kubectl` configurado para o cluster:
  ```bash
  aws eks update-kubeconfig --name togglemaster-dev-eks --region us-east-1
  ```
- Account ID da conta AWS definido nos manifests:
  ```bash
  ./scripts/set-account-id.sh <SEU_ACCOUNT_ID>
  ```

## 0. Pré-requisitos do cluster

Os `base.yaml` dos serviços usam `secretRef` e o `ingress.yaml` usa a classe
`nginx`. Instale antes:

### Secrets (1 por serviço)
```bash
kubectl create secret generic auth-service-secret -n auth \
  --from-literal=DATABASE_URL='postgres://toggle_user:SENHA@HOST:5432/auth?sslmode=disable' \
  --from-literal=MASTER_KEY='sua-master-key'

kubectl create secret generic flag-service-secret -n flag \
  --from-literal=DATABASE_URL='postgres://toggle_user:SENHA@HOST:5432/flags?sslmode=disable'

kubectl create secret generic targeting-service-secret -n targeting \
  --from-literal=DATABASE_URL='postgres://toggle_user:SENHA@HOST:5432/targeting?sslmode=disable'

kubectl create secret generic evaluation-service-secret -n evaluation \
  --from-literal=REDIS_URL='redis://ENDERECO_REDIS:6379/0' \
  --from-literal=SERVICE_API_KEY='tm_key_...'

kubectl create secret generic analytics-service-secret -n analytics \
  --from-literal=AWS_ACCESS_KEY_ID='...' \
  --from-literal=AWS_SECRET_ACCESS_KEY='...'
```
> Os endpoints (RDS/Redis/SQS) saem do `terraform output`:
> ```bash
> cd terraform && terraform output
> ```

### NGINX Ingress Controller
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/aws/deploy.yaml
```

## 1. Instalar o ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.13.4/manifests/install.yaml
```

Aguardar os pods ficarem prontos:
```bash
kubectl get pods -n argocd -w
```

## 2. Acessar a interface Web

```bash
# Obter a senha inicial (admin)
kubectl get secret argocd-initial-admin-secret -n argocd \
  -o jsonpath="{.data.password}" | base64 -d; echo

# Port forwarding para o serviço do server
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Acessar: `https://localhost:8080` (usuário: `admin`)

> Para expor via LoadBalancer/Ingress (mais parecido com produção):
> ```bash
> kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "LoadBalancer"}}'
> ```

## 3. Configurar o repositório no ArgoCD

Na interface ou via CLI (`argocd login`), adicione o repositório do monorepo:

```bash
argocd repo add https://github.com/enzorooschqueiroz/fiap-toggle-master.git \
  --username <usuario> --password <token>
```

## 4. Criar a Application (GitOps)

O manifesto pronto está em `gitops/argocd/application.yaml`:
```bash
kubectl apply -f gitops/argocd/application.yaml
```

> **Nota:** como o `application.yaml` fica dentro da pasta `gitops/` que o
> ArgoCD sincroniza, ele se gerencia a si mesmo. Para evitar isso, aplique o
> Application manualmente (comando acima) e, opcionalmente, adicione exclusão
> do namespace argocd no configmap `argocd-cm`:
> ```yaml
> resource.exclusions: |
>   - apiGroups:
>       - argoproj.io
>     kinds:
>       - Application
>     clusters:
>       - '*'
> ```

Isso criará uma `Application` que monitora a pasta `gitops/` do repositório
com auto-sync habilitado (prune + selfHeal).

## 5. Verificação

### Via CLI:
```bash
argocd app list
argocd app sync togglemaster
argocd app status togglemaster
```

### Via UI:
- Na interface do ArgoCD, você verá a aplicação `togglemaster` gerenciando
  os 5 microsserviços (auth, flag, targeting, evaluation, analytics).
- Exemplos de URL:
  - auth: `http://<LB-host>/auth/health`
  - flag: `http://<LB-host>/flags/health`
  - etc.

## Fluxo automático (CI → GitOps → Cluster)

1. CI roda (build, test, security scan) e faz push da imagem no ECR.
2. CI atualiza a tag no `gitops/<service>/base.yaml` (job `update-gitops`).
3. ArgoCD detecta a mudança no repositório (polling) e faz sync automático.
4. New rollout no cluster com a nova versão.