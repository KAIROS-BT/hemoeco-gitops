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
GH_ORG="KAIROS-BT"
GH_REPO="hemoeco-gitops"
APP_NAME="hemoeco-gitops"
TARGET_RG="rg-kaione"
LOCATION="eastus"
STATE_CONTAINER="tfstate"

# NO hardcodees el ID de suscripcion: descubri el real buscando donde vive
# el RG objetivo. (Apuntar a un SUB inexistente da "la suscripcion no existe"
# al crear roles, aunque seas Owner.)
SUB=""
for s in $(az account list --query "[?state=='Enabled'].id" -o tsv); do
  if az group show -n "$TARGET_RG" --subscription "$s" -o none 2>/dev/null; then SUB="$s"; break; fi
done
az account set --subscription "$SUB"
TENANT=$(az account show --query tenantId -o tsv)

# El estado de Terraform vive en el mismo RG objetivo; nombre global unico:
STATE_RG="$TARGET_RG"
STATE_SA="sttfstatekaione$RANDOM"
echo "SUB=$SUB TENANT=$TENANT STATE_SA=$STATE_SA"
```

### 1. Backend remoto para el estado de Terraform

```bash
# El RG objetivo ya existe; creamos el storage del estado dentro de el.
az storage account create -n "$STATE_SA" -g "$STATE_RG" -l "$LOCATION" \
  --sku Standard_LRS --min-tls-version TLS1_2 --allow-blob-public-access false
# Container via account key: evita el 403 por propagacion de RBAC de plano de datos.
KEY=$(az storage account keys list -g "$STATE_RG" -n "$STATE_SA" --query "[0].value" -o tsv)
az storage container create -n "$STATE_CONTAINER" \
  --account-name "$STATE_SA" --account-key "$KEY"
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

> Nota: en repos **privados**, tanto la branch protection como la aprobacion
> del environment requieren GitHub Pro/Team (o hacer el repo publico). Sin eso,
> el check `validate` igual corre y se ve verde/rojo en cada PR, pero no se puede
> *forzar* como bloqueo de merge ni exigir aprobacion manual del deploy.

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
