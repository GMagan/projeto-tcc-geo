#!/usr/bin/env python3
"""Publica as skills (Markdown) como agentes no Open WebUI: "prompt as code".

Para cada arquivo em skills/ cria ou atualiza um modelo do Open WebUI cujo
prompt de sistema é persona + skill. Assim o texto que governa o agente é o
que está versionado no Git, e não o que alguém digitou na interface.

Precisa de OPENWEBUI_URL, OPENWEBUI_API_KEY e MODELO_OLLAMA (ver .env.example).

ATENÇÃO: as rotas /api/v1/models/* seguem o rascunho do projeto e não foram
exercitadas contra uma instância em execução; confira com a versão do seu
Open WebUI. As tools MCP de cada agente são ligadas na interface
(Workspace > Modelos > Ferramentas), depois de registrar o servidor MCP.

Uso:  python scripts/sync_skills.py [--simular]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from agente import carregar_skill, listar_skills, montar_prompt  # noqa: E402


def carga(skill: dict, modelo_base: str) -> dict:
    return {
        "id": f"plano-{skill['id'].replace('_', '-')}",
        "name": f"Plano de manejo {skill['topico']}: {skill['titulo']}",
        "base_model_id": modelo_base,
        "meta": {
            "description": f"Skill do tópico {skill['topico']} do plano de manejo. Roteiro: {skill['roteiro']}.",
            "capabilities": {"function_calling": True},
        },
        "params": {"system": montar_prompt(skill), "temperature": 0, "function_calling": "native"},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--simular", action="store_true", help="só mostra o que seria enviado")
    args = ap.parse_args()

    url = os.environ.get("OPENWEBUI_URL", "http://localhost:8080").rstrip("/")
    chave = os.environ.get("OPENWEBUI_API_KEY", "")
    modelo_base = os.environ.get("MODELO_OLLAMA", "qwen2.5:7b")
    if not chave and not args.simular:
        sys.exit("defina OPENWEBUI_API_KEY (ou use --simular)")
    cabecalhos = {"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}

    for ident in listar_skills():
        dados = carga(carregar_skill(ident), modelo_base)
        if args.simular:
            print(f"[simulação] {dados['id']}: {dados['name']} ({len(dados['params']['system'])} caracteres de prompt)")
            continue
        resposta = requests.post(f"{url}/api/v1/models/model/update", params={"id": dados["id"]}, headers=cabecalhos, json=dados, timeout=30)
        if resposta.status_code in (400, 401, 404):  # ainda não existe: cria
            resposta = requests.post(f"{url}/api/v1/models/create", headers=cabecalhos, json=dados, timeout=30)
        resposta.raise_for_status()
        print(f"[ok] {dados['id']}")


if __name__ == "__main__":
    main()
