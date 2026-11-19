"""Modelos de linguagem atrás de uma interface única: conversar(mensagens, tools) -> mensagem."""
from __future__ import annotations

import time

import httpx


class ModeloRoteirizado:
    """Devolve respostas fixas, na ordem. Usado nos testes do orquestrador."""

    nome = "roteirizado"

    def __init__(self, respostas: list[dict]):
        self._respostas = list(respostas)
        self.recebido: list[dict] = []

    def conversar(self, mensagens: list[dict], tools: list[dict] | None) -> dict:
        self.recebido.append({"mensagens": [dict(m) for m in mensagens], "tools": tools})
        if not self._respostas:
            return {"role": "assistant", "content": ""}
        return dict(self._respostas.pop(0))


class ModeloOpenAI:
    """Qualquer servidor com a API /v1/chat/completions (Ollama, vLLM, LM Studio, OpenAI...)."""

    def __init__(self, base_url: str, modelo: str, chave: str = "sem-chave", temperatura: float = 0.0, semente: int = 42, timeout_s: float = 900):
        self.base_url = base_url.rstrip("/")
        self.nome = modelo
        self.chave = chave
        self.temperatura = temperatura
        self.semente = semente
        self.timeout_s = timeout_s

    def conversar(self, mensagens: list[dict], tools: list[dict] | None) -> dict:
        corpo = {"model": self.nome, "messages": mensagens, "temperature": self.temperatura, "seed": self.semente}
        if tools:
            corpo["tools"] = tools
        inicio = time.perf_counter()
        resposta = httpx.post(
            f"{self.base_url}/chat/completions", json=corpo,
            headers={"Authorization": f"Bearer {self.chave}"}, timeout=self.timeout_s,
        )
        resposta.raise_for_status()
        dados = resposta.json()
        mensagem = dados["choices"][0]["message"]
        mensagem["_uso"] = {**(dados.get("usage") or {}), "segundos": round(time.perf_counter() - inicio, 2)}
        return mensagem
