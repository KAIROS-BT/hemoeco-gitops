# Gobernanza de infraestructura por GitOps — Hemoeco (Terraform)

Motor de gobernanza que condiciona el despliegue al cumplimiento del estandar de
etiquetado, con auditoria continua del inventario. Nada se despliega fuera de
estandar; la cobertura de etiquetas se mantiene visible de forma automatica.

## Como funciona

1. Un cambio de infraestructura entra como Pull Request.
2. El motor valida que cada recurso declare `workload`, `ambiente` y `owner` con
   valores validos (gate en CI + validacion nativa de Terraform). Si falta una
   etiqueta o el valor es invalido, bloquea el merge.
3. Al integrar a `main`, autenticacion federada (OIDC, sin secretos almacenados en
   el repo), `terraform plan` y `apply` unicamente si el gate paso.
4. En paralelo, una auditoria programada recorre toda la suscripcion vía Resource
   Graph y reporta los recursos sin cobertura completa.

## Estructura

```
infra/providers.tf            azurerm + backend remoto + OIDC
infra/variables.tf            variables; validacion nativa de etiquetas
infra/main.tf                 recurso de ejemplo (tags = var.common_tags)
infra/tags.auto.tfvars.json   etiquetas (objetivo del gate)
infra/terraform.tfvars        config no-tags de ejemplo
policy/tagging-standard.json  estandar de etiquetado
scripts/validate_tags.py      gate de etiquetas
scripts/audit_coverage.py     auditoria de cobertura
.github/workflows/*.yml       validate (PR), deploy (main), audit (programada)
```

## Configuracion paso a paso

Todo en Cloud Shell. Re-deriva las variables al inicio de cada sesion.

### 0. Variables

```bash
SUB="6b2cf929-f0d7-4d7d-91e6-c79622ac195d"
TENANT=$(az account show --query tenantId -o tsv)
GH_ORG="<tu-org>"
GH_REPO="<tu-repo>"
APP_NAME="hemoeco-gitops"
LOCATION="westus"
TARGET_RG="rg-hemoecocloud-shared-001"
STATE_RG="rg-tfstate-001"
STATE_SA="sthemoecotfstate$RANDOM"   # nombre global unico
STATE_CONTAINER="tfstate"
az account set --subscription "$SUB"
```

### 1. Backend remoto para el estado de Terraform

```bash
az group create -n "$STATE_RG" -l "$LOCATION"
az storage account create -n "$STATE_SA" -g "$STATE_RG" -l "$LOCATION" \
  --sku Standard_LRS --min-tls-version TLS1_2 --allow-blob-public-access false
az storage container create -n "$STATE_CONTAINER" \
  --account-name "$STATE_SA" --auth-mode login
```

### 2. Identidad federada (sin client secret)

```bash
APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
az ad sp create --id "$APP_ID"
```

### 3. Permisos minimos

```bash
# Desplegar en el RG objetivo
az role assignment create --assignee "$APP_ID" --role "Contributor" \
  --scope "/subscriptions/$SUB/resourceGroups/$TARGET_RG"
# Estado remoto
az role assignment create --assignee "$APP_ID" --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/$SUB/resourceGroups/$STATE_RG/providers/Microsoft.Storage/storageAccounts/$STATE_SA"
# Auditoria de inventario (lectura de toda la suscripcion)
az role assignment create --assignee "$APP_ID" --role "Reader" \
  --scope "/subscriptions/$SUB"
```

### 4. Federated credentials (PR, main, environment)

```bash
for entry in \
  "github-pr:repo:${GH_ORG}/${GH_REPO}:pull_request" \
  "github-main:repo:${GH_ORG}/${GH_REPO}:ref:refs/heads/main" \
  "github-env-prod:repo:${GH_ORG}/${GH_REPO}:environment:prod"; do
  NAME="${entry%%:*}"; SUBJECT="${entry#*:}"
  cat > /tmp/fic.json <<EOF
{"name":"$NAME","issuer":"https://token.actions.githubusercontent.com",
 "subject":"$SUBJECT","audiences":["api://AzureADTokenExchange"]}
EOF
  az ad app federated-credential create --id "$APP_ID" --parameters /tmp/fic.json
done
```

Para que sirve cada uno:
- `github-pr`: el job de PR (validacion). No autentica a Azure, pero deja el flujo
  preparado por si agregas `terraform plan` en PR.
- `github-main`: la auditoria programada corre desde `main`.
- `github-env-prod`: el job de despliegue corre dentro del environment `prod`, asi
  que su subject OIDC es `environment:prod`.

### 5. Secrets y variables del repo (GitHub CLI)

```bash
gh secret  set AZURE_CLIENT_ID       --body "$APP_ID"  -R "$GH_ORG/$GH_REPO"
gh secret  set AZURE_TENANT_ID       --body "$TENANT"  -R "$GH_ORG/$GH_REPO"
gh secret  set AZURE_SUBSCRIPTION_ID --body "$SUB"     -R "$GH_ORG/$GH_REPO"
gh variable set AZURE_RESOURCE_GROUP --body "$TARGET_RG"     -R "$GH_ORG/$GH_REPO"
gh variable set TFSTATE_RG           --body "$STATE_RG"      -R "$GH_ORG/$GH_REPO"
gh variable set TFSTATE_SA           --body "$STATE_SA"      -R "$GH_ORG/$GH_REPO"
gh variable set TFSTATE_CONTAINER    --body "$STATE_CONTAINER" -R "$GH_ORG/$GH_REPO"
```

### 6. Environment con aprobacion + branch protection

```bash
# Environment prod (agrega reviewers en la UI: Settings > Environments > prod)
gh api -X PUT "repos/$GH_ORG/$GH_REPO/environments/prod" >/dev/null

# Branch protection: exige el check validate-tags para mergear a main
gh api -X PUT "repos/$GH_ORG/$GH_REPO/branches/main/protection" \
  -H "Accept: application/vnd.github+json" \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=validate' \
  -f 'enforce_admins=true' \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -f 'restrictions='
```

## Guion de la demo en vivo

1. Abre un PR cambiando `ambiente` a `produccion` y borra `owner` en
   `infra/tags.auto.tfvars.json`. El check `validate` falla y bloquea el merge.
   Muestra el bloqueo: ese es el control de gobernanza.
2. Corrige a `ambiente: prod` y repon `owner`. El check pasa, el merge se habilita.
3. Dispara `audit-inventory` manual (workflow_dispatch). En el resumen del job
   aparece la tabla de recursos sin etiquetado completo de toda la suscripcion.

## Seguridad

- Autenticacion por OIDC federado; no hay client secret en el repositorio.
- Despliegue detras del environment `prod`, al que puedes exigir aprobacion manual.
- Estado de Terraform en backend remoto cifrado; consultas de inventario read-only.
