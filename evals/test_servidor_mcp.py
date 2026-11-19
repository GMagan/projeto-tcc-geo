"""Testes do servidor MCP: o que o agente enxerga pelo protocolo.

O cliente MCP conversa com o servidor em processo (sem rede), mas pelas mesmas
mensagens `tools/list` e `tools/call` que o Open WebUI ou outro cliente usaria.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from conftest import E0, N0, lonlat
from mcp import Client

import geotools as gt
import server

TOOLS_DO_RECORTE = {
    "listar_camadas", "carregar_camada", "validar_geometria", "reprojetar",
    "calcular_area", "coordenadas_extremas", "municipios_intersectados",
    "calcular_area_zonas", "percentual_por_zona", "zona_da_coordenada",
    "distancia_ate", "intersecao", "calcular_buffer", "calcular_buffer_coordenada",
    "uso_solo_na_area", "gerar_mapa", "consultar_roteiro",
}


@pytest.fixture(scope="module")
def servidor(cat, tmp_path_factory):
    indice = gt.IndiceBM25([{"fonte": "Roteiro", "pagina": 33, "texto": "Zona de Conservação: ambientes naturais de relevante interesse ecológico."}])
    return server.criar_servidor(cat, indice, pasta_mapas=tmp_path_factory.mktemp("mapas"))


def chamar(servidor, tool: str, argumentos: dict) -> dict:
    async def _chamar():
        async with Client(servidor) as cliente:
            resultado = await cliente.call_tool(tool, argumentos)
            return json.loads(resultado.content[0].text)

    return asyncio.run(_chamar())


def test_servidor_publica_todas_as_tools_do_recorte(servidor):
    async def _listar():
        async with Client(servidor) as cliente:
            return (await cliente.list_tools()).tools

    tools = asyncio.run(_listar())
    assert {t.name for t in tools} == TOOLS_DO_RECORTE
    assert all(t.description and len(t.description) > 30 for t in tools), "toda tool precisa de descrição para o modelo"


def test_tool_devolve_json_com_o_mesmo_numero_do_motor(servidor, cat):
    r = chamar(servidor, "calcular_area", {"camada": "zoneamento", "feicao": "ZAA"})
    assert r["status"] == "sucesso"
    assert r["area_ha"] == gt.calcular_area(cat, "zoneamento", "ZAA")["area_ha"] == 40.00


def test_erro_de_uso_volta_como_mensagem_para_o_agente_corrigir(servidor):
    r = chamar(servidor, "calcular_area", {"camada": "limite"})
    assert r["status"] == "erro"
    assert "limite_uc" in r["mensagem"]  # diz quais camadas existem


def test_zona_da_coordenada_pelo_protocolo(servidor):
    lon, lat = lonlat(E0 + 100, N0 + 100)
    r = chamar(servidor, "zona_da_coordenada", {"lon": lon, "lat": lat})
    assert r["sigla"] == "ZC"


def test_consultar_roteiro_pelo_protocolo(servidor):
    r = chamar(servidor, "consultar_roteiro", {"consulta": "zona de conservação"})
    assert r["trechos"][0]["pagina"] == 33


def test_gerar_mapa_pelo_protocolo_grava_na_pasta_configurada(servidor):
    r = chamar(servidor, "gerar_mapa", {"tema": "zoneamento"})
    assert r["status"] == "sucesso" and r["arquivo_png"] == "mapa_zoneamento.png"
