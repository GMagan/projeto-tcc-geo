# Uso normal: coloque os dados da UC em dados/entrada/ e rode `make`.
# `make ajuda` lista os demais comandos.
PY := .venv/bin/python
ENV := .venv/.instalado  # marca que as dependências estão instaladas
LLM_BASE_URL ?= http://localhost:11434/v1
LLM_MODELO ?= qwen2.5:7b

.PHONY: rodar ajuda importar ia testes resultados exemplo servidor avaliar-llm avaliar-baseline juiz-llm sync subir diagramas

rodar: $(ENV) importar ## (padrão) importa dados/entrada, testa e gera os resultados
	$(MAKE) --no-print-directory resultados
	@ls resultados/llm/*/agente.jsonl >/dev/null 2>&1 || echo "ATENÇÃO: o agente com IA ainda não foi avaliado. Instale o Ollama e rode 'make avaliar-llm avaliar-baseline' (ver README, parte 2)."

$(ENV): mcp-python/requirements.txt requirements-dev.txt
	python3 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements-dev.txt
	@touch $(ENV)

ajuda:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/'

importar: $(ENV) ## lê dados/entrada/ (pergunta o que faltar)
	$(PY) scripts/importar_dados.py

ia: $(ENV) ## modo IA: a IA identifica os arquivos de dados/entrada/ (precisa de Ollama), depois igual ao `make`
	LLM_BASE_URL=$(LLM_BASE_URL) LLM_MODELO=$(LLM_MODELO) $(PY) scripts/importar_com_ia.py
	$(MAKE) --no-print-directory resultados

testes: $(ENV) ## roda os testes do programa
	$(PY) -m pytest -q -p no:cacheprovider

resultados: $(ENV) ## calcula tabelas e mapas da UC importada (e roda os testes)
	$(PY) scripts/gerar_resultados.py

exemplo: ## copia o exemplo do PE Santa Clara para dados/entrada/ (só se estiver vazia)
	@if [ -n "$$(ls -A dados/entrada 2>/dev/null)" ]; then echo "dados/entrada/ não está vazia: esvazie antes de copiar o exemplo"; exit 1; fi
	mkdir -p dados/entrada
	cp -r exemplo/santa_clara/entrada/. dados/entrada/
	@echo "exemplo copiado. Rode: make"

servidor: $(ENV) ## sobe o servidor MCP em http://localhost:8001/mcp
	$(PY) mcp-python/server.py

avaliar-llm: $(ENV) ## avalia o agente com IA (precisa de Ollama rodando)
	$(PY) evals/rodar_agente.py --base-url $(LLM_BASE_URL) --modelo $(LLM_MODELO) --condicao agente

avaliar-baseline: $(ENV) ## mesma avaliação, modelo sem tools
	$(PY) evals/rodar_agente.py --base-url $(LLM_BASE_URL) --modelo $(LLM_MODELO) --condicao sem_tools

juiz-llm: $(ENV) ## juiz por modelo (DeepEval); defina JUIZ_MODELO
	$(PY) -m pip install -q -r requirements-juiz.txt
	$(PY) -m pytest evals/test_llm_quality.py -m llm

sync: $(ENV) ## publica as skills no Open WebUI
	$(PY) scripts/sync_skills.py

subir: ## sobe Open WebUI e servidor MCP com Docker
	docker compose up -d --build

diagramas: $(ENV) ## desenha os diagramas SADT e de arquitetura
	$(PY) scripts/gerar_diagramas.py
