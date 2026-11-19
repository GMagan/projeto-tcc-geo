#!/usr/bin/env python3
"""Servidor MCP do motor espacial (TCC-GeoWorker).

Expõe as funções determinísticas de `geotools` como tools do Model Context
Protocol. O modelo de linguagem escolhe a tool e os argumentos; todo número
sai daqui. Cada chamada fica registrada em JSONL para auditoria.

Variáveis de ambiente:
  GEO_CATALOGO   caminho do catalogo.yaml         (padrão: ../dados/catalogo.yaml)
  GEO_ROTEIRO    índice JSONL do roteiro          (padrão: ../conhecimento/roteiro_icmbio_2018.jsonl)
  GEO_SAIDAS     pasta dos mapas gerados          (padrão: ../resultados/mapas)
  GEO_AUDITORIA  arquivo JSONL das chamadas       (padrão: ../resultados/auditoria_tools.jsonl)
  MCP_TRANSPORT  stdio | streamable-http | sse    (padrão: streamable-http)
  MCP_HOST, MCP_PORT                              (padrão: 0.0.0.0, 8001)

Uso:
  python server.py                      # HTTP em http://0.0.0.0:8001/mcp
  MCP_TRANSPORT=stdio python server.py  # para clientes que iniciam o processo
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import Callable

from mcp.server.mcpserver import MCPServer

import geotools as gt

RAIZ = Path(__file__).resolve().parents[1]

INSTRUCOES = (
    "Motor espacial determinístico para o plano de manejo de uma unidade de conservação (UC), com os dados carregados pelo usuário. "
    "Toda área, distância, percentual e coordenada deve vir de uma tool deste servidor; "
    "nunca estime valores. Áreas saem em hectares e distâncias em metros, calculadas em "
    "SIRGAS 2000 / UTM, no fuso da UC (informado em crs_calculo). Use listar_camadas para ver os dados disponíveis; se faltar uma camada, diga ao usuário qual dado carregar. "
    "Quando a resposta trouxer provisorio=true, avise que o dado é provisório."
)


def criar_servidor(
    cat: gt.Catalogo,
    indice: gt.IndiceBM25 | None = None,
    pasta_mapas: str | Path | None = None,
    auditoria: str | Path | None = None,
) -> MCPServer:
    """Monta o servidor com as tools ligadas a um catálogo (o real ou um de teste)."""
    srv = MCPServer("TCC-GeoWorker", instructions=INSTRUCOES, version="0.1.0")
    arquivo_auditoria = Path(auditoria) if auditoria else None

    def executar(nome: str, funcao: Callable[..., dict], **argumentos) -> dict:
        """Roda a função do motor; erro de uso volta como mensagem para o agente corrigir."""
        inicio = time.perf_counter()
        try:
            resultado = funcao(**argumentos)
        except gt.ErroGeo as erro:
            resultado = {"status": "erro", "ferramenta": nome, "mensagem": str(erro)}
        except Exception as erro:  # falha inesperada: informa sem derrubar o servidor
            resultado = {"status": "erro", "ferramenta": nome, "mensagem": f"falha interna: {type(erro).__name__}: {erro}"}
        if arquivo_auditoria:
            arquivo_auditoria.parent.mkdir(parents=True, exist_ok=True)
            registro = {
                "quando": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "tool": nome,
                "argumentos": argumentos,
                "status": resultado["status"],
                "ms": round(1000 * (time.perf_counter() - inicio), 1),
                "resultado": resultado,
            }
            with arquivo_auditoria.open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
        return resultado

    # ---------------------------------------------------------------- 1.2 base cartográfica
    @srv.tool()
    def listar_camadas() -> dict:
        """Lista as camadas de dados disponíveis (nome, tipo, descrição e se é provisória). Use antes de qualquer cálculo para saber os nomes exatos das camadas."""
        return executar("listar_camadas", lambda: gt.listar_camadas(cat))

    @srv.tool()
    def carregar_camada(camada: str) -> dict:
        """Resume uma camada: número de feições, tipo de geometria, sistema de referência (CRS), extensão, campos, feições, fonte e licença. `camada` é o nome dado por listar_camadas."""
        return executar("carregar_camada", lambda **a: gt.carregar_camada(cat, **a), camada=camada)

    @srv.tool()
    def validar_geometria(camada: str) -> dict:
        """Verifica se as geometrias da camada são válidas (sem laços nem autointerseção) e informa quanto a correção altera a área."""
        return executar("validar_geometria", lambda **a: gt.validar_geometria(cat, **a), camada=camada)

    @srv.tool()
    def reprojetar(camada: str, epsg_destino: int = 0) -> dict:
        """Converte a camada para outro sistema de referência e devolve as extensões de origem e destino. Padrão (0): o sistema de trabalho da UC, SIRGAS 2000 / UTM no fuso dela."""
        return executar("reprojetar", lambda **a: gt.reprojetar(cat, **a), camada=camada, epsg_destino=epsg_destino)

    # ---------------------------------------------------------------- 3.1 ficha técnica
    @srv.tool()
    def calcular_area(camada: str, feicao: str = "") -> dict:
        """Calcula a área em hectares e o perímetro em km de uma camada. `feicao` (opcional) restringe a uma feição pela sigla ou nome, por exemplo camada='zoneamento', feicao='ZC'. Camadas úteis: limite_uc, zoneamento, zona_amortecimento; as demais estão em listar_camadas."""
        return executar("calcular_area", lambda **a: gt.calcular_area(cat, **a), camada=camada, feicao=feicao)

    @srv.tool()
    def coordenadas_extremas(camada: str = "limite_uc") -> dict:
        """Devolve os pontos mais ao norte, sul, leste e oeste da camada em graus, minutos e segundos (SIRGAS 2000), como na ficha técnica do plano de manejo."""
        return executar("coordenadas_extremas", lambda **a: gt.coordenadas_extremas(cat, **a), camada=camada)

    @srv.tool()
    def municipios_intersectados(camada: str = "limite_uc") -> dict:
        """Lista os municípios abrangidos pela camada, com a área (ha) e o percentual dela em cada município (malha do IBGE)."""
        return executar("municipios_intersectados", lambda **a: gt.municipios_intersectados(cat, **a), camada=camada)

    # ---------------------------------------------------------------- 5.1 a 5.5 zoneamento
    @srv.tool()
    def calcular_area_zonas() -> dict:
        """Monta a tabela de áreas (ha) de todas as zonas de manejo da UC, com o total, a conferência com o limite da UC e a área da zona de amortecimento."""
        return executar("calcular_area_zonas", lambda: gt.calcular_area_zonas(cat))

    @srv.tool()
    def percentual_por_zona() -> dict:
        """Calcula a participação percentual de cada zona de manejo na área total da UC (a soma dá 100)."""
        return executar("percentual_por_zona", lambda: gt.percentual_por_zona(cat))

    @srv.tool()
    def zona_da_coordenada(lon: float, lat: float) -> dict:
        """Diz em qual zona de manejo cai um ponto. `lon` e `lat` em graus decimais SIRGAS 2000, negativos no hemisfério sul e a oeste de Greenwich. Informa também se o ponto está na UC, na zona de amortecimento e a distância até o limite."""
        return executar("zona_da_coordenada", lambda **a: gt.zona_da_coordenada(cat, **a), lon=lon, lat=lat)

    # ---------------------------------------------------------------- 5.4 a 5.6 distância, interseção, buffer
    @srv.tool()
    def distancia_ate(camada_origem: str, camada_destino: str, feicao_origem: str = "", feicao_destino: str = "") -> dict:
        """Mede a menor distância em metros entre a origem e cada feição da camada de destino. Exemplo: camada_origem='zoneamento', feicao_origem='ZI', camada_destino=<uma camada de listar_camadas>."""
        return executar(
            "distancia_ate", lambda **a: gt.distancia_ate(cat, **a),
            camada_origem=camada_origem, camada_destino=camada_destino, feicao_origem=feicao_origem, feicao_destino=feicao_destino,
        )

    @srv.tool()
    def intersecao(camada_a: str, camada_b: str, feicao_a: str = "", feicao_b: str = "") -> dict:
        """Calcula a parte comum entre duas camadas: área em ha (polígono com polígono) ou comprimento em km (linha com polígono). Exemplo: camada_a=<camada de estradas fornecida>, camada_b='limite_uc' dá o comprimento de estradas dentro da UC."""
        return executar(
            "intersecao", lambda **a: gt.intersecao(cat, **a),
            camada_a=camada_a, camada_b=camada_b, feicao_a=feicao_a, feicao_b=feicao_b,
        )

    @srv.tool()
    def calcular_buffer(camada: str, distancia_m: float, feicao: str = "") -> dict:
        """Gera uma faixa de `distancia_m` metros em volta da camada e devolve a área total (ha) e a área só da faixa. Exemplo: camada='limite_uc', distancia_m=3000 para o entorno de 3 km da UC."""
        return executar("calcular_buffer", lambda **a: gt.calcular_buffer(cat, **a), camada=camada, distancia_m=distancia_m, feicao=feicao)

    @srv.tool()
    def calcular_buffer_coordenada(lon: float, lat: float, raio_metros: float) -> dict:
        """Calcula a área de influência circular (ha) em volta de uma coordenada. `lon` e `lat` em graus decimais; `raio_metros` em metros. O raio é medido sobre o elipsoide (círculo geodésico)."""
        return executar("calcular_buffer_coordenada", gt.calcular_buffer_coordenada, lon=lon, lat=lat, raio_metros=raio_metros)

    # ---------------------------------------------------------------- 5.3 e 5.6 uso do solo
    @srv.tool()
    def uso_solo_na_area(camada: str, feicao: str = "") -> dict:
        """Dá a área (ha) e o percentual de cada classe de uso e cobertura da terra dentro da camada ou de uma feição dela. Exemplo: camada='zoneamento', feicao='ZAA'."""
        return executar("uso_solo_na_area", lambda **a: gt.uso_solo_na_area(cat, **a), camada=camada, feicao=feicao)

    # ---------------------------------------------------------------- 6.1 mapa
    @srv.tool()
    def gerar_mapa(tema: str = "zoneamento") -> dict:
        """Gera o mapa em PNG e PDF com legenda, grade UTM, escala e norte. `tema` é 'zoneamento' (zonas internas) ou 'zona_amortecimento' (entorno). Devolve os nomes dos arquivos gravados."""
        return executar("gerar_mapa", lambda **a: gt.gerar_mapa(cat, pasta_saida=pasta_mapas, **a), tema=tema)

    # ---------------------------------------------------------------- controle normativo (RAG)
    @srv.tool()
    def consultar_roteiro(consulta: str, k: int = 3) -> dict:
        """Busca no Roteiro Metodológico do ICMBio (2018) os trechos que tratam do assunto pedido, com a página para citação. Use para definições e normas das zonas; nunca para números de área."""
        if indice is None:
            return {"status": "erro", "ferramenta": "consultar_roteiro", "mensagem": "índice do roteiro não carregado (rode scripts/construir_rag.py)"}
        return executar("consultar_roteiro", lambda **a: gt.consultar_roteiro(indice, **a), consulta=consulta, k=k)

    return srv


def servidor_padrao() -> MCPServer:
    """Servidor com os dados reais do projeto, configurado por variáveis de ambiente."""
    cat = gt.Catalogo(os.environ.get("GEO_CATALOGO", RAIZ / "dados" / "catalogo.yaml"))
    roteiro = Path(os.environ.get("GEO_ROTEIRO", RAIZ / "conhecimento" / "roteiro_icmbio_2018.jsonl"))
    indice = gt.IndiceBM25.de_jsonl(roteiro) if roteiro.exists() else None
    return criar_servidor(
        cat,
        indice,
        pasta_mapas=os.environ.get("GEO_SAIDAS", RAIZ / "resultados" / "mapas"),
        auditoria=os.environ.get("GEO_AUDITORIA", RAIZ / "resultados" / "auditoria_tools.jsonl"),
    )


if __name__ == "__main__":
    transporte = os.environ.get("MCP_TRANSPORT", "streamable-http")
    servidor = servidor_padrao()
    if transporte == "stdio":
        servidor.run("stdio")
    else:
        servidor.run(transporte, host=os.environ.get("MCP_HOST", "0.0.0.0"), port=int(os.environ.get("MCP_PORT", "8001")))
