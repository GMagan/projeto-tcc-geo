"""Motor espacial determinístico do projeto (camada T0).

Cada função recebe um `Catalogo` e devolve um dicionário pronto para virar
JSON. Nenhuma depende de modelo de linguagem: o servidor MCP (`server.py`)
apenas as expõe como tools.
"""
from .base import carregar_camada, listar_camadas, reprojetar, validar_geometria
from .catalogo import Catalogo
from .erros import ErroGeo
from .mapas import gerar_mapa
from .medidas import br, calcular_area, coordenadas_extremas, graus_para_gms, municipios_intersectados
from .rag import IndiceBM25, consultar_roteiro
from .sobreposicao import (
    buffer_geodesico,
    calcular_buffer,
    calcular_buffer_coordenada,
    distancia_ate,
    intersecao,
)
from .uso_solo import uso_solo_na_area
from .zoneamento import calcular_area_zonas, percentual_por_zona, zona_da_coordenada

__all__ = [
    "Catalogo",
    "ErroGeo",
    "IndiceBM25",
    "br",
    "buffer_geodesico",
    "calcular_area",
    "calcular_area_zonas",
    "calcular_buffer",
    "calcular_buffer_coordenada",
    "carregar_camada",
    "consultar_roteiro",
    "coordenadas_extremas",
    "distancia_ate",
    "gerar_mapa",
    "graus_para_gms",
    "intersecao",
    "listar_camadas",
    "municipios_intersectados",
    "percentual_por_zona",
    "reprojetar",
    "uso_solo_na_area",
    "validar_geometria",
    "zona_da_coordenada",
]
