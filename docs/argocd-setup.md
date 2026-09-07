# Setup do ArgoCD no Cluster EKS

Este guia cobre a instalação do ArgoCD e a configuração para que ele monitore
a pasta `gitops/` do monorepo.

## Pré-requisitos
- Cluster EKS provisionado (via Terraform da fase 3)
- `kubectl` configurado para o cluster:
  ```bash
  aws eks update-kubeconfig --name togglemaster-dev-eks --region us-east-1
  ```

## 1. Instalar o ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
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
argocd repo add https://github.com/<SEU_USUARIO>/toggle-master.git \
  --username <usuario> --password <token>
```

## 4. Criar a Application (GitOps)

O manifesto pronta está em `gitops/argocd/application.yaml`. Edite o
`repoURL` com seu usuário e aplique:

```bash
kubectl apply -f gitops/argocd/application.yaml
```

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