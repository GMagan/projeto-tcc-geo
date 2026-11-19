"""Testes do orquestrador do agente, com um modelo roteirizado no lugar do LLM.

O modelo roteirizado devolve respostas fixas, na ordem. Assim se testa o laço
de orquestração (Fases 1 a 3 do diagrama A0) sem depender de inferência.
"""
from __future__ import annotations

import json

import pytest

import geotools as gt
import server
from agente import ModeloRoteirizado, carregar_skill, executar


@pytest.fixture(scope="module")
def servidor(cat, tmp_path_factory):
    return server.criar_servidor(cat, gt.IndiceBM25([]), pasta_mapas=tmp_path_factory.mktemp("mapas"))


def pedir_tool(nome: str, argumentos: dict | str, ident: str = "c1") -> dict:
    args = argumentos if isinstance(argumentos, str) else json.dumps(argumentos)
    return {"role": "assistant", "content": "", "tool_calls": [{"id": ident, "type": "function", "function": {"name": nome, "arguments": args}}]}


def responder(texto: str) -> dict:
    return {"role": "assistant", "content": texto}


def test_agente_chama_a_tool_pedida_e_registra_o_resultado_no_rastro(servidor):
    modelo = ModeloRoteirizado([pedir_tool("calcular_area", {"camada": "zoneamento", "feicao": "ZAA"}), responder("A ZAA tem 40,00 ha.")])
    rastro = executar("Qual a área da ZAA?", carregar_skill("zona_adequacao"), modelo, servidor)
    assert rastro["resposta"] == "A ZAA tem 40,00 ha."
    assert rastro["chamadas"][0]["tool"] == "calcular_area"
    assert rastro["chamadas"][0]["argumentos"] == {"camada": "zoneamento", "feicao": "ZAA"}
    assert rastro["chamadas"][0]["resultado"]["area_ha"] == 40.00
    assert rastro["esgotou_passos"] is False


def test_resultado_da_tool_volta_ao_modelo_como_mensagem(servidor):
    modelo = ModeloRoteirizado([pedir_tool("calcular_area", {"camada": "limite_uc"}), responder("ok")])
    executar("Área?", carregar_skill("ficha_tecnica"), modelo, servidor)
    mensagens_da_segunda_chamada = modelo.recebido[1]["mensagens"]
    devolvida = mensagens_da_segunda_chamada[-1]
    assert devolvida["role"] == "tool" and devolvida["tool_call_id"] == "c1"
    assert json.loads(devolvida["content"])["area_ha"] == 200.00


def test_prompt_de_sistema_junta_persona_e_skill(servidor):
    modelo = ModeloRoteirizado([responder("ok")])
    executar("Oi", carregar_skill("zoneamento"), modelo, servidor)
    sistema = modelo.recebido[0]["mensagens"][0]
    assert sistema["role"] == "system"
    assert "Nenhum número sai de você" in sistema["content"]  # persona
    assert "Distribuição das zonas" in sistema["content"]  # skill


def test_modelo_so_enxerga_as_tools_autorizadas_pela_skill(servidor):
    modelo = ModeloRoteirizado([responder("ok")])
    skill = carregar_skill("ficha_tecnica")
    executar("Oi", skill, modelo, servidor)
    oferecidas = {t["function"]["name"] for t in modelo.recebido[0]["tools"]}
    assert oferecidas == set(skill["tools"])
    assert "calcular_buffer" not in oferecidas


def test_tool_fora_da_skill_e_recusada_sem_executar(servidor):
    modelo = ModeloRoteirizado([pedir_tool("calcular_buffer", {"camada": "limite_uc", "distancia_m": 100}), responder("ok")])
    rastro = executar("Buffer?", carregar_skill("ficha_tecnica"), modelo, servidor)
    assert rastro["chamadas"][0]["resultado"]["status"] == "erro"
    assert "não autorizada" in rastro["chamadas"][0]["resultado"]["mensagem"]


def test_argumentos_que_nao_sao_json_viram_erro_para_o_modelo_corrigir(servidor):
    modelo = ModeloRoteirizado([pedir_tool("calcular_area", "{camada: limite_uc"), responder("desisto")])
    rastro = executar("Área?", carregar_skill("ficha_tecnica"), modelo, servidor)
    assert rastro["chamadas"][0]["resultado"]["status"] == "erro"
    assert rastro["resposta"] == "desisto"


def test_laco_para_no_limite_de_passos(servidor):
    modelo = ModeloRoteirizado([pedir_tool("calcular_area", {"camada": "limite_uc"}, f"c{i}") for i in range(10)])
    rastro = executar("Área?", carregar_skill("ficha_tecnica"), modelo, servidor, max_passos=3)
    assert rastro["esgotou_passos"] is True
    assert len(rastro["chamadas"]) == 3


def test_condicao_sem_tools_nao_oferece_ferramentas_nem_skill(servidor):
    modelo = ModeloRoteirizado([responder("uns 600 ha")])
    rastro = executar("Área?", None, modelo, servidor, contexto="POLYGON ((0 0, 1 0, 1 1, 0 0))")
    assert modelo.recebido[0]["tools"] is None
    assert "POLYGON" in modelo.recebido[0]["mensagens"][-1]["content"]
    assert rastro["chamadas"] == [] and rastro["skill"] is None
