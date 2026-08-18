# Gobernanza de infraestructura por GitOps — Terraform + Azure

Motor de gobernanza que condiciona el despliegue de infraestructura al cumplimiento
del estándar de etiquetado, con auditoría continua del inventario. Nada se despliega
fuera de estándar; la cobertura de etiquetas se mantiene visible de forma automática.

> **Estado de esta entrega.** El repositorio se entrega **desconectado de cualquier
> suscripción de Azure**: no contiene credenciales, IDs de suscripción ni nombres de
> recursos de ningún entorno previo. Los workflows que hablan con Azure vienen
> desactivados y requieren dos pasos explícitos para habilitarse
> (ver [Conectar tu suscripción de Azure](#conectar-tu-suscripción-de-azure)).

---

## Cómo funciona

1. Un cambio de infraestructura entra como **Pull Request**.
2. El motor valida que cada recurso declare `workload`, `ambiente` y `owner` con
   valores válidos (gate en CI + validación nativa de Terraform). Si falta una
   etiqueta o el valor es inválido, el check falla y bloquea el merge.
3. Al integrar a `main`, autenticación federada (**OIDC, sin secretos almacenados en
   el repositorio**), `terraform plan` y `apply` únicamente si el gate pasó.
4. En paralelo, una auditoría recorre toda la suscripción vía **Azure Resource Graph**
   y reporta los recursos sin cobertura completa de etiquetas.

Cada ejecución publica un **reporte visual en Markdown** en el resumen del job
(pestaña *Actions* → run → *Summary*): tabla de etiquetas con ✅/❌, resumen del plan
(agregar / cambiar / destruir) y detalle del recurso desplegado.

---

## Estructura

```
infra/providers.tf                azurerm + backend remoto + OIDC
infra/variables.tf                variables; validación nativa de etiquetas
infra/main.tf                     recurso de ejemplo (tags = var.common_tags)
infra/outputs.tf                  salidas que alimentan el reporte de despliegue
infra/tags.auto.tfvars.json       etiquetas de gobernanza — OBJETIVO DEL GATE (versionado)
infra/terraform.tfvars.example    plantilla de configuración local (copiar y editar)
policy/tagging-standard.json      estándar de etiquetado
scripts/validate_tags.py          gate de etiquetas → Markdown + exit code
scripts/audit_coverage.py         auditoría de cobertura sobre la suscripción
scripts/deploy_report.py          reporte de despliegue → Markdown
.github/workflows/validate-tags.yml   PR — no toca Azure, corre siempre
.github/workflows/deploy.yml          manual — requiere ENABLE_AZURE=true
.github/workflows/audit-inventory.yml manual — requiere ENABLE_AZURE=true
```

### Qué se versiona y qué no

| Archivo | ¿Versionado? | Por qué |
|---|:---:|---|
| `infra/tags.auto.tfvars.json` | **Sí** | Es el objetivo del gate: el estándar se audita en el PR. |
| `infra/terraform.tfvars` | **No** (`.gitignore`) | Describe *tu* entorno: RG, región, nombre de storage. |
| `infra/terraform.tfvars.example` | **Sí** | Plantilla para que cada quien cree la suya. |
| `*.tfstate`, `.terraform/`, `tfplan` | **No** | Estado y artefactos; el estado vive en el backend remoto. |

---

## Qué viene desactivado y por qué

| Workflow | Trigger original | Trigger en la entrega | Toca Azure |
|---|---|---|:---:|
| `validate-tags` | Pull Request | **Pull Request** (sin cambios) + manual | No |
| `deploy` | `push` a `main` | **Solo manual** + `ENABLE_AZURE=true` | Sí |
| `audit-inventory` | `schedule` semanal | **Solo manual** + `ENABLE_AZURE=true` | Sí |

`validate-tags` sigue activo porque **no se autentica contra Azure**: solo valida
formato, sintaxis de Terraform y cumplimiento de etiquetas. Funciona en un fork recién
creado, sin configurar nada. Es la parte demostrable del día uno.

`deploy` y `audit-inventory` necesitan **dos condiciones simultáneas**:

1. Lanzarlos a mano desde *Actions* → *Run workflow*.
2. La variable de repositorio `ENABLE_AZURE` con valor `true`.

Si falta cualquiera de las dos, el job de `preflight` escribe en el resumen qué falta
y el despliegue **no se ejecuta**. Es un seguro contra apuntar sin querer a una
suscripción equivocada.

---

## Puesta en marcha

### 1. Haz un fork

**Desde la interfaz web:** botón **Fork** arriba a la derecha → elige la organización
o cuenta destino → *Create fork*.

**Desde la terminal**, con [GitHub CLI](https://cli.github.com/):

```bash
gh repo fork <org-origen>/<repo-origen> --org <TU-ORG> --clone
cd <repo-origen>
```

Si prefieres un repositorio nuevo e independiente en vez de un fork (recomendado si
no quieres que quede enlazado al original):

```bash
gh repo create <TU-ORG>/<TU-REPO> --private --clone
# copia el contenido de la entrega dentro y haz el primer commit
```

> **Nota sobre forks:** GitHub **no copia** los secrets ni las variables del
> repositorio original al fork — eso es deliberado y es bueno. Tendrás que crear los
> tuyos en el paso *Conectar tu suscripción*. GitHub también **deshabilita Actions**
> en los forks por defecto: entra a la pestaña **Actions** del fork y pulsa
> *I understand my workflows, go ahead and enable them*.

### 2. Configuración local

```bash
cp infra/terraform.tfvars.example infra/terraform.tfvars
# edita infra/terraform.tfvars con tu grupo de recursos, región y nombre de storage
```

`infra/terraform.tfvars` está en `.gitignore`: describe tu entorno y **no debe
versionarse**. En CI esos mismos valores llegan por variables del repositorio.

Ajusta también las etiquetas de gobernanza en `infra/tags.auto.tfvars.json`
(estas **sí** se versionan — son lo que el gate audita):

```json
{
  "common_tags": {
    "workload": "finops-demo",
    "ambiente": "test",
    "owner": "TI",
    "proyecto": "hemoeco"
  }
}
```

Y el estándar en sí, si quieres exigir otras etiquetas, en `policy/tagging-standard.json`.

### 3. Prueba el gate sin tocar Azure

El gate corre en tu máquina con solo Python 3 — sin credenciales, sin Terraform:

```bash
python3 scripts/validate_tags.py infra/tags.auto.tfvars.json policy/tagging-standard.json
echo "exit code: $?"   # 0 = cumple, 1 = incumple
```

Abre un Pull Request con cualquier cambio en `infra/` y verás el check `validate`
correr solo, con su tabla de etiquetas en el resumen del job.

---

## Conectar tu suscripción de Azure

Todo lo siguiente se ejecuta en **Azure Cloud Shell** (o cualquier terminal con `az`
y `gh` autenticados). Re-deriva las variables al inicio de cada sesión.

### 0. Variables de trabajo

```bash
GH_ORG="<TU-ORG-O-USUARIO>"          # dueño del fork
GH_REPO="<TU-REPO>"                  # nombre del repositorio
APP_NAME="<TU-REPO>-oidc"            # nombre de la app registration
TARGET_RG="<TU-GRUPO-DE-RECURSOS>"   # RG donde se despliega (debe existir)
LOCATION="eastus"                    # región del RG
STORAGE_NAME="<TU-STORAGE-DEMO>"     # 3-24 caracteres, minúsculas y números
STATE_CONTAINER="tfstate"

# NO hardcodees el ID de suscripción: descúbrelo buscando dónde vive el RG objetivo.
# (Apuntar a una suscripción inexistente da "la suscripción no existe" al crear
# roles, aunque seas Owner — error difícil de diagnosticar.)
SUB=""
for s in $(az account list --query "[?state=='Enabled'].id" -o tsv); do
  if az group show -n "$TARGET_RG" --subscription "$s" -o none 2>/dev/null; then SUB="$s"; break; fi
done
[ -z "$SUB" ] && echo "ERROR: no encontré el RG '$TARGET_RG' en ninguna suscripción habilitada."
az account set --subscription "$SUB"
TENANT=$(az account show --query tenantId -o tsv)

# El estado de Terraform vive en el mismo RG objetivo; el nombre debe ser único global:
STATE_RG="$TARGET_RG"
STATE_SA="sttfstate$RANDOM$RANDOM"
echo "SUB=$SUB TENANT=$TENANT STATE_SA=$STATE_SA"
```

> Guarda el valor de `STATE_SA`: lo necesitas en el paso 5 y no se puede re-derivar.

### 1. Backend remoto para el estado de Terraform

```bash
az storage account create -n "$STATE_SA" -g "$STATE_RG" -l "$LOCATION" \
  --sku Standard_LRS --min-tls-version TLS1_2 --allow-blob-public-access false

# Crea el container con account key: evita el 403 por propagación del RBAC de
# plano de datos, que tarda unos minutos en hacerse efectivo.
KEY=$(az storage account keys list -g "$STATE_RG" -n "$STATE_SA" --query "[0].value" -o tsv)
az storage container create -n "$STATE_CONTAINER" \
  --account-name "$STATE_SA" --account-key "$KEY"
unset KEY   # la key no se guarda en ningún lado: el pipeline usa OIDC
```

### 2. Identidad federada (sin client secret)

```bash
APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
az ad sp create --id "$APP_ID"
echo "APP_ID=$APP_ID"
```

### 3. Permisos mínimos

```bash
# Desplegar únicamente en el RG objetivo
az role assignment create --assignee "$APP_ID" --role "Contributor" \
  --scope "/subscriptions/$SUB/resourceGroups/$TARGET_RG"

# Escribir el estado remoto
az role assignment create --assignee "$APP_ID" --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/$SUB/resourceGroups/$STATE_RG/providers/Microsoft.Storage/storageAccounts/$STATE_SA"

# Auditoría de inventario (solo lectura de toda la suscripción)
az role assignment create --assignee "$APP_ID" --role "Reader" \
  --scope "/subscriptions/$SUB"
```

Deliberadamente el service principal **no** es Owner ni Contributor a nivel
suscripción. Ver [Notas de diseño](#notas-de-diseño) sobre el efecto que esto tiene
en el registro de resource providers.

### 4. Credenciales federadas (PR, main, environment)

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
rm -f /tmp/fic.json
```

Para qué sirve cada una:

- `github-pr` — el job de PR. Hoy no se autentica a Azure, pero deja el flujo listo
  por si agregas un `terraform plan` en PR.
- `github-main` — la auditoría de inventario, que corre desde `main`.
- `github-env-prod` — el job de despliegue corre dentro del environment `prod`, así
  que su *subject* OIDC es `environment:prod` y no `ref:refs/heads/main`.

### 5. Secrets y variables del repositorio

```bash
gh secret   set AZURE_CLIENT_ID       --body "$APP_ID"          -R "$GH_ORG/$GH_REPO"
gh secret   set AZURE_TENANT_ID       --body "$TENANT"          -R "$GH_ORG/$GH_REPO"
gh secret   set AZURE_SUBSCRIPTION_ID --body "$SUB"             -R "$GH_ORG/$GH_REPO"

gh variable set AZURE_RESOURCE_GROUP  --body "$TARGET_RG"       -R "$GH_ORG/$GH_REPO"
gh variable set AZURE_LOCATION        --body "$LOCATION"        -R "$GH_ORG/$GH_REPO"
gh variable set STORAGE_ACCOUNT_NAME  --body "$STORAGE_NAME"    -R "$GH_ORG/$GH_REPO"
gh variable set TFSTATE_RG            --body "$STATE_RG"        -R "$GH_ORG/$GH_REPO"
gh variable set TFSTATE_SA            --body "$STATE_SA"        -R "$GH_ORG/$GH_REPO"
gh variable set TFSTATE_CONTAINER     --body "$STATE_CONTAINER" -R "$GH_ORG/$GH_REPO"
```

Referencia completa:

| Nombre | Tipo | Contenido |
|---|---|---|
| `AZURE_CLIENT_ID` | secret | App ID de la identidad federada |
| `AZURE_TENANT_ID` | secret | Tenant de Entra ID |
| `AZURE_SUBSCRIPTION_ID` | secret | Suscripción destino |
| `AZURE_RESOURCE_GROUP` | variable | RG donde se despliega |
| `AZURE_LOCATION` | variable | Región del RG |
| `STORAGE_ACCOUNT_NAME` | variable | Nombre del storage de ejemplo |
| `TFSTATE_RG` | variable | RG del backend de estado |
| `TFSTATE_SA` | variable | Storage account del estado |
| `TFSTATE_CONTAINER` | variable | Container del estado (`tfstate`) |
| `TFSTATE_KEY` | variable *(opcional)* | Nombre del blob de estado (por defecto `hemoeco-gitops.tfstate`) |
| `ENABLE_AZURE` | variable | Interruptor maestro. Ver paso 7. |

### 6. Environment con aprobación y branch protection

```bash
# Environment prod (agrega reviewers en la UI: Settings → Environments → prod)
gh api -X PUT "repos/$GH_ORG/$GH_REPO/environments/prod" >/dev/null

# Branch protection: exige el check validate para poder mergear a main
gh api -X PUT "repos/$GH_ORG/$GH_REPO/branches/main/protection" \
  -H "Accept: application/vnd.github+json" \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=validate' \
  -f 'enforce_admins=true' \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -f 'restrictions='
```

> **Requisito de plan.** En repositorios **privados**, tanto la branch protection como
> la aprobación del environment requieren **GitHub Pro / Team / Enterprise**. Sin eso
> el check `validate` igual corre y se ve verde o rojo en cada PR, pero no se puede
> *forzar* como bloqueo de merge ni exigir aprobación manual del despliegue. En
> repositorios **públicos** ambas cosas están disponibles en el plan gratuito.

### 7. Activar el despliegue

Último interruptor, a propósito separado del resto:

```bash
gh variable set ENABLE_AZURE --body "true" -R "$GH_ORG/$GH_REPO"
```

Verifica antes de nada, con el despliegue todavía apagado:

```bash
gh workflow run deploy -R "$GH_ORG/$GH_REPO"
gh run watch -R "$GH_ORG/$GH_REPO"
```

Con `ENABLE_AZURE` sin definir, el resumen del job te dirá exactamente qué falta y
**no** ejecutará ningún `terraform apply`. Cuando el preflight salga en verde, ya
puedes lanzarlo de verdad.

Para volver a apagarlo en cualquier momento:

```bash
gh variable delete ENABLE_AZURE -R "$GH_ORG/$GH_REPO"
```

### 8. (Opcional) Restaurar los triggers automáticos

Cuando el pipeline esté validado y quieras GitOps completo:

- **`deploy.yml`** — reemplaza `on: workflow_dispatch:` por:

  ```yaml
  on:
    push:
      branches: [main]
      paths: ['infra/**']
    workflow_dispatch:
  ```

- **`audit-inventory.yml`** — descomenta el bloque `schedule` que ya está en el archivo.

El guard de `ENABLE_AZURE` sigue en pie aunque restaures los triggers: es una segunda
línea de defensa independiente.

---

## Uso diario

```bash
git checkout -b cambio/lo-que-sea
# edita infra/ o policy/
git commit -am "infra: ..." && git push -u origin cambio/lo-que-sea
gh pr create --fill
```

1. El check `validate` corre solo y publica la tabla de etiquetas en el resumen del PR.
2. Si falla, el merge queda bloqueado (con branch protection activa).
3. Al mergear a `main`, lanza `deploy` — a mano mientras conserves la configuración de
   entrega, o automáticamente si restauraste el trigger `push`.
4. Revisa el reporte de despliegue en *Actions* → run → *Summary*.

---

## Guion de demostración

1. Abre un PR cambiando `ambiente` a `produccion` y borrando `owner` en
   `infra/tags.auto.tfvars.json`. El check `validate` falla: la tabla marca ❌ en las
   dos filas y el merge queda bloqueado. **Ese es el control de gobernanza.**
2. Corrige a `"ambiente": "test"` y repón `owner`. El check pasa, el merge se habilita.
3. Dispara `audit-inventory` a mano (*Run workflow*). En el resumen aparece la tabla de
   recursos sin etiquetado completo de toda la suscripción.

---

## Seguridad

- **Sin secretos en el repositorio.** La autenticación es OIDC federado: GitHub emite
  un token de vida corta que Azure canjea. No hay client secret, ni access key de
  storage, ni perfil de publicación almacenado en el código.
- **Mínimo privilegio.** El service principal es `Contributor` solo sobre el RG
  objetivo, `Storage Blob Data Contributor` solo sobre el storage del estado, y
  `Reader` sobre la suscripción para poder auditar. No puede crear ni borrar fuera
  de ese perímetro.
- **Credenciales federadas acotadas por *subject*.** Cada credencial está atada a un
  contexto concreto (`pull_request`, `ref:refs/heads/main`, `environment:prod`): un
  workflow de otra rama o de otro repositorio no puede canjear el token.
- **Despliegue detrás del environment `prod`**, al que puedes exigir aprobación manual.
- **Estado de Terraform en backend remoto** cifrado en reposo, con acceso por Azure AD
  (no por account key) y sin acceso público al blob.
- **`terraform.tfvars` fuera del control de versiones**, junto con `*.tfstate`,
  `.terraform/`, `*.env`, `*.pem` y `*.key` (ver `.gitignore`).
- **Los forks no heredan secrets.** Si alguien forkea este repositorio, no se lleva
  ninguna credencial: tiene que configurar la suya.

---

## Notas de diseño

**`resource_provider_registrations = "none"`** en `infra/providers.tf`. Por defecto el
provider `azurerm` intenta registrar resource providers al arrancar, lo que exige
`Microsoft.*/register/action` a nivel de suscripción — permiso que un SP de mínimo
privilegio no tiene, y que hace fallar el `plan` con un 403. Con el auto-registro
desactivado, el plan corre limpio. **Si agregas recursos de un resource provider que
la suscripción todavía no tenga registrado**, regístralo una vez con una identidad
que sí pueda:

```bash
az provider register --namespace Microsoft.<LoQueSea>
```

**Doble validación de etiquetas.** El gate en Python (`scripts/validate_tags.py`)
bloquea en CI y produce el reporte visual; los bloques `validation` de
`infra/variables.tf` bloquean en `terraform plan`, incluso si alguien ejecuta
Terraform fuera del pipeline. La redundancia es intencional: el gate es la
experiencia, la validación nativa es la garantía.

---

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `deploy` termina sin desplegar y el resumen dice "Despliegue desactivado" | `ENABLE_AZURE` no vale `true` | `gh variable set ENABLE_AZURE --body true` |
| `AADSTS70021: No matching federated identity record found` | El *subject* de la credencial federada no coincide con el contexto del job | Revisa el paso 4: `environment:prod` para el deploy, `ref:refs/heads/main` para la auditoría |
| `plan` falla con 403 al registrar un resource provider | El SP no tiene `register/action` a nivel suscripción | Ya está mitigado con `resource_provider_registrations = "none"`; registra el RP a mano (ver Notas de diseño) |
| `403` al crear el container del estado | Propagación del RBAC de plano de datos | Crea el container con account key, como en el paso 1 |
| `The subscription '...' could not be found` al crear roles | El ID de suscripción no corresponde al RG objetivo | Usa el descubrimiento automático del paso 0; no hardcodees el ID |
| `terraform plan` local pide `resource_group_name` | Falta `infra/terraform.tfvars` | `cp infra/terraform.tfvars.example infra/terraform.tfvars` y edítalo |
| Los workflows no aparecen tras el fork | GitHub deshabilita Actions en los forks | Pestaña *Actions* → *I understand my workflows, go ahead and enable them* |

---

## Requisitos

- Cuenta de Azure con permisos para crear app registrations y asignar roles
  (Owner o User Access Administrator sobre la suscripción, para el setup inicial).
- [Azure CLI](https://learn.microsoft.com/cli/azure/) y
  [GitHub CLI](https://cli.github.com/) — o simplemente Azure Cloud Shell, que trae
  ambos.
- Terraform ≥ 1.6 si quieres ejecutar planes localmente (el pipeline usa 1.9.8).
- Python 3 para correr el gate de etiquetas fuera de CI.
