#!/usr/bin/env python3
"""Reporte de cobertura de etiquetas sobre toda la suscripcion (read-only).

Usa Azure Resource Graph (az graph query). Emite Markdown a stdout
(apto para GITHUB_STEP_SUMMARY).
"""
import json
import subprocess
import sys

KQL = """
Resources
| extend t = tolower(tostring(tags))
| extend faltan = pack_array(
    iff(t has '"workload"', '', 'workload'),
    iff(t has '"ambiente"', '', 'ambiente'),
    iff(t has '"owner"',    '', 'owner'))
| extend faltan = set_difference(faltan, dynamic(['']))
| where array_length(faltan) > 0
| project name, type, resourceGroup, faltan
| order by type asc
"""


def main():
    try:
        out = subprocess.check_output(
            ["az", "graph", "query", "-q", KQL, "--first", "1000", "-o", "json"],
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print("Error ejecutando az graph query:", e)
        sys.exit(1)

    rows = json.loads(out).get("data", [])
    print("## Cobertura de etiquetado - recursos no conformes\n")
    if not rows:
        print("Todos los recursos cumplen el estandar (workload, ambiente, owner).")
        return
    print(f"**{len(rows)} recurso(s) sin cobertura completa**\n")
    print("| Recurso | Tipo | Grupo de recursos | Etiquetas faltantes |")
    print("|---|---|---|---|")
    for r in rows:
        print(f"| {r['name']} | {r['type']} | {r['resourceGroup']} | {', '.join(r['faltan'])} |")


if __name__ == "__main__":
    main()
