"""Orquestrador do agente: liga um modelo de linguagem às tools do servidor MCP.

É a versão sem interface do que o Open WebUI faz no uso interativo. Serve para
rodar a avaliação de forma automática e gravar o rastro completo de cada execução.
"""
from .modelos import ModeloOpenAI, ModeloRoteirizado
from .orquestrador import executar
from .skills import carregar_skill, listar_skills, montar_prompt

__all__ = ["ModeloOpenAI", "ModeloRoteirizado", "carregar_skill", "executar", "listar_skills", "montar_prompt"]
