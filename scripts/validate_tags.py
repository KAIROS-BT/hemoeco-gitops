#!/usr/bin/env python3
"""Valida que las etiquetas declaradas cumplan el estandar de gobernanza.

Uso: validate_tags.py <tags.auto.tfvars.json> <tagging-standard.json>
Emite un reporte Markdown (apto para GITHUB_STEP_SUMMARY) y sale con codigo 1
si hay incumplimiento (bloquea el merge / deploy).
"""
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rule_desc(rule):
    if rule["type"] == "enum":
        return "enum: " + " / ".join(rule["allowed"])
    if rule.get("minLength"):
        return f"texto (min {rule['minLength']})"
    return "texto"


def main(tfvars_path, policy_path):
    policy = load(policy_path)["requiredTags"]
    data = load(tfvars_path)
    tags = data.get("common_tags", data)

    rows = []
    errors = []
    for key, rule in policy.items():
        declared = tags.get(key)
        if declared in (None, ""):
            errors.append(f"falta etiqueta requerida: `{key}`")
            rows.append((key, rule_desc(rule), "— (falta)", "❌"))
            continue
        ok = True
        if rule["type"] == "enum" and declared not in rule["allowed"]:
            errors.append(f"`{key}` = `{declared}` invalido; permitidos: {rule['allowed']}")
            ok = False
        if rule.get("minLength") and len(str(declared)) < rule["minLength"]:
            errors.append(f"`{key}` = `{declared}` demasiado corto (min {rule['minLength']})")
            ok = False
        rows.append((key, rule_desc(rule), str(declared), "✅" if ok else "❌"))

    extra = [k for k in tags if k not in policy]

    print("## 🔖 Validación de etiquetas de gobernanza\n")
    print("| Etiqueta | Requisito | Valor declarado | Estado |")
    print("|---|---|---|:---:|")
    for name, req, val, st in rows:
        print(f"| `{name}` | {req} | {val} | {st} |")
    for k in extra:
        print(f"| `{k}` | _(extra, opcional)_ | {tags[k]} | ➕ |")
    print()

    if errors:
        print("### ❌ Incumplimiento — despliegue bloqueado\n")
        for e in errors:
            print(f"- {e}")
        print()
        sys.exit(1)
    print("### ✅ Cumple el estándar — despliegue habilitado")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
