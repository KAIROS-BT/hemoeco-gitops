#!/usr/bin/env python3
"""Valida que las etiquetas declaradas cumplan el estandar de gobernanza.

Uso: validate_tags.py <tags.auto.tfvars.json> <tagging-standard.json>
Sale con codigo 1 si hay incumplimiento (bloquea el merge / deploy).
"""
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(tfvars_path, policy_path):
    policy = load(policy_path)["requiredTags"]
    data = load(tfvars_path)
    tags = data.get("common_tags", data)

    errors = []
    for key, rule in policy.items():
        if key not in tags or tags[key] in (None, ""):
            errors.append(f"falta etiqueta requerida: '{key}'")
            continue
        val = tags[key]
        if rule["type"] == "enum" and val not in rule["allowed"]:
            errors.append(f"'{key}'='{val}' invalido; permitidos: {rule['allowed']}")
        if rule.get("minLength") and len(str(val)) < rule["minLength"]:
            errors.append(f"'{key}'='{val}' demasiado corto (min {rule['minLength']})")

    print("Etiquetas declaradas:", json.dumps(tags, ensure_ascii=False))
    if errors:
        print("\nINCUMPLIMIENTO - despliegue bloqueado:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("\nCumple el estandar de etiquetado. Despliegue habilitado.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
