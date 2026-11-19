"""Laço de orquestração: as três fases do diagrama A0.

  Fase 1  o modelo interpreta a pergunta sob a skill e pede uma tool (function calling);
  Fase 2  a tool roda no servidor MCP, sem participação do modelo;
  Fase 3  o modelo redige a resposta a partir do resultado devolvido.

Tudo o que acontece fica no rastro devolvido: mensagens, chamadas, resultados e tempos.
"""
from __future__ import annotations

import asyncio
import json
import time

from mcp import Client

from .skills import montar_prompt

PROMPT_SEM_SKILL = "Você é um assistente. Responda em português do Brasil, de forma direta."


def _para_openai(tool) -> dict:
    return {"type": "function", "function": {"name": tool.name, "description": tool.description or "", "parameters": tool.input_schema}}


async def _executar(pergunta: str, skill: dict | None, modelo, servidor, max_passos: int, contexto: str | None) -> dict:
    inicio = time.perf_counter()
    usuario = pergunta if not contexto else f"{pergunta}\n\nDados:\n{contexto}"
    mensagens = [{"role": "system", "content": montar_prompt(skill) if skill else PROMPT_SEM_SKILL}, {"role": "user", "content": usuario}]
    rastro = {
        "pergunta": pergunta, "skill": skill["id"] if skill else None, "modelo": getattr(modelo, "nome", "?"),
        "contexto": contexto, "resposta": "", "chamadas": [], "passos": 0, "esgotou_passos": False,
        "uso": {"prompt_tokens": 0, "completion_tokens": 0, "segundos_modelo": 0.0},
    }

    async with Client(servidor) as cliente:
        autorizadas, tools = set(), None
        if skill:
            autorizadas = set(skill.get("tools", []))
            tools = [_para_openai(t) for t in (await cliente.list_tools()).tools if t.name in autorizadas]

        for _ in range(max_passos):
            mensagem = modelo.conversar(mensagens, tools)
            uso = mensagem.pop("_uso", {})
            rastro["uso"]["prompt_tokens"] += uso.get("prompt_tokens", 0)
            rastro["uso"]["completion_tokens"] += uso.get("completion_tokens", 0)
            rastro["uso"]["segundos_modelo"] += uso.get("segundos", 0.0)
            rastro["passos"] += 1
            mensagens.append(mensagem)
            pedidos = mensagem.get("tool_calls") or []
            if not pedidos:
                rastro["resposta"] = mensagem.get("content") or ""
                break
            for pedido in pedidos:
                nome = pedido["function"]["name"]
                t0 = time.perf_counter()
                argumentos, resultado = pedido["function"].get("arguments"), None
                try:
                    argumentos = json.loads(argumentos) if isinstance(argumentos, str) else (argumentos or {})
                except json.JSONDecodeError as erro:
                    resultado = {"status": "erro", "mensagem": f"argumentos inválidos (JSON malformado): {erro}"}
                if resultado is None and nome not in autorizadas:
                    resultado = {"status": "erro", "mensagem": f"tool '{nome}' não autorizada nesta skill; use: {', '.join(sorted(autorizadas))}"}
                if resultado is None:
                    retorno = await cliente.call_tool(nome, argumentos)
                    texto = retorno.content[0].text if retorno.content else ""
                    try:
                        resultado = json.loads(texto)
                    except json.JSONDecodeError:
                        resultado = {"status": "erro", "mensagem": texto}
                rastro["chamadas"].append({"tool": nome, "argumentos": argumentos, "resultado": resultado, "ms": round(1000 * (time.perf_counter() - t0), 1)})
                mensagens.append({"role": "tool", "tool_call_id": pedido.get("id", ""), "content": json.dumps(resultado, ensure_ascii=False)})
        else:
            rastro["esgotou_passos"] = True

    rastro["mensagens"] = mensagens
    rastro["segundos"] = round(time.perf_counter() - inicio, 2)
    return rastro


def executar(pergunta: str, skill: dict | None, modelo, servidor, max_passos: int = 6, contexto: str | None = None) -> dict:
    """Roda uma pergunta. Com `skill`, o agente tem persona, skill e tools; sem ela, só o modelo e o `contexto`."""
    return asyncio.run(_executar(pergunta, skill, modelo, servidor, max_passos, contexto))
