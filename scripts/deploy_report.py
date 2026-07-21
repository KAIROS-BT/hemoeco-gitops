#!/usr/bin/env python3
"""Reporte Markdown del despliegue para GITHUB_STEP_SUMMARY.

Uso: deploy_report.py <plan.txt> <terraform-output.json>
Lee el resumen del `terraform plan` y los outputs del estado y emite Markdown.
Opcional via entorno: GH_SHA, GH_ACTOR (contexto del commit que disparo el deploy).
"""
import json
import os
import re
import sys


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def read_outputs(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main(plan_path, outputs_path):
    plan = read_text(plan_path)
    outputs = read_outputs(outputs_path)

    def val(key, default="—"):
        return outputs.get(key, {}).get("value", default)

    m = re.search(r"Plan:\s*(\d+) to add, (\d+) to change, (\d+) to destroy", plan)
    if m:
        add, chg, dst = m.groups()
    elif "No changes." in plan:
        add, chg, dst = "0", "0", "0"
    else:
        add, chg, dst = "?", "?", "?"

    print("## 🚀 Reporte de despliegue\n")

    sha = os.environ.get("GH_SHA", "")
    actor = os.environ.get("GH_ACTOR", "")
    ctx = []
    if sha:
        ctx.append(f"commit `{sha[:7]}`")
    if actor:
        ctx.append(f"disparado por @{actor}")
    if ctx:
        print("> " + " · ".join(ctx) + "\n")

    print("### Resumen del plan\n")
    print("| 🟢 Agregar | 🟡 Cambiar | 🔴 Destruir |")
    print("|:---:|:---:|:---:|")
    print(f"| {add} | {chg} | {dst} |\n")

    name = val("storage_account_name")
    if name != "—":
        print("### Recurso desplegado\n")
        print("| Propiedad | Valor |")
        print("|---|---|")
        print(f"| Storage account | `{name}` |")
        print(f"| Resource group | `{val('resource_group')}` |")
        print(f"| Location | `{val('location')}` |")
        print(f"| Resource ID | `{val('resource_id')}` |\n")

        tags = val("applied_tags", {})
        if isinstance(tags, dict) and tags:
            print("### 🔖 Etiquetas aplicadas al recurso\n")
            print("| Etiqueta | Valor |")
            print("|---|---|")
            for k in sorted(tags):
                print(f"| `{k}` | {tags[k]} |")
            print()

    print("**✅ Despliegue completado — infraestructura sincronizada con `main`.**")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
