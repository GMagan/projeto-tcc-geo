"""Tópico 1.2 do plano: base cartográfica (carregar, validar, reprojetar)."""
from __future__ import annotations

import shapely
from pyproj import CRS
from pyproj.exceptions import CRSError
from shapely import make_valid

from .catalogo import Catalogo
from .erros import ErroGeo


def _epsg(crs) -> str:
    codigo = crs.to_epsg()
    return f"EPSG:{codigo}" if codigo else crs.to_string()


def listar_camadas(cat: Catalogo) -> dict:
    camadas = [
        {"camada": nome, "tipo": "vetor", "descricao": m.get("descricao", ""), "provisorio": cat.procedencia(nome)["provisorio"]}
        for nome, m in cat.camadas.items()
    ] + [
        {"camada": nome, "tipo": "raster", "descricao": m.get("descricao", ""), "provisorio": m.get("provisorio", False)}
        for nome, m in cat.rasters.items()
    ]
    return {"status": "sucesso", "ferramenta": "listar_camadas", "crs_trabalho": cat.crs, "camadas": camadas}


def carregar_camada(cat: Catalogo, camada: str) -> dict:
    original = cat.ler(camada, no_crs_de_trabalho=False)
    meta = cat.meta(camada)
    gdf = cat.ler(camada)
    return {
        "status": "sucesso",
        "ferramenta": "carregar_camada",
        "camada": camada,
        "descricao": meta.get("descricao", ""),
        "n_feicoes": len(gdf),
        "tipo_geometria": sorted(original.geom_type.unique().tolist()),
        "crs_origem": _epsg(original.crs),
        "crs_trabalho": cat.crs,
        "extensao_utm": [round(float(v), 2) for v in gdf.total_bounds],
        "campos": [c for c in gdf.columns if c != "geometry"],
        "feicoes": cat.rotulos(camada)[:30],
        "fonte": meta.get("fonte", ""),
        "licenca": meta.get("licenca", ""),
        "provisorio": meta.get("provisorio", False),
    }


def validar_geometria(cat: Catalogo, camada: str) -> dict:
    """Aponta geometrias inválidas e quanto a correção (make_valid) muda a área."""
    cat.meta(camada)
    gdf = cat.ler(camada, no_crs_de_trabalho=False).to_crs(cat.epsg)
    invalidas = gdf[~gdf.geometry.is_valid]
    corrigidas = invalidas.geometry.apply(make_valid)
    return {
        "status": "sucesso",
        "ferramenta": "validar_geometria",
        "camada": camada,
        "n_feicoes": len(gdf),
        "n_invalidas": len(invalidas),
        "motivos": [shapely.is_valid_reason(g) for g in invalidas.geometry],
        "area_original_m2": round(float(invalidas.geometry.area.sum()), 2),
        "area_corrigida_m2": round(float(corrigidas.area.sum()), 2),
        "correcao": "shapely.make_valid, aplicada automaticamente na leitura das camadas",
        "crs_calculo": cat.crs,
    }


def reprojetar(cat: Catalogo, camada: str, epsg_destino: int | None = None) -> dict:
    """Converte a camada para outro CRS (padrão: o CRS de trabalho) e informa as extensões."""
    cat.meta(camada)
    destino = int(epsg_destino or cat.epsg)
    try:
        CRS.from_epsg(destino)
    except CRSError as erro:
        raise ErroGeo(f"EPSG:{destino} não é um sistema de referência conhecido") from erro
    original = cat.ler(camada, no_crs_de_trabalho=False)
    convertida = original.to_crs(destino)
    return {
        "status": "sucesso",
        "ferramenta": "reprojetar",
        "camada": camada,
        "n_feicoes": len(original),
        "crs_origem": _epsg(original.crs),
        "crs_destino": f"EPSG:{destino}",
        "nome_crs_destino": CRS.from_epsg(destino).name,
        "extensao_origem": [round(float(v), 7) for v in original.total_bounds],
        "extensao_destino": [round(float(v), 3) for v in convertida.total_bounds],
    }
