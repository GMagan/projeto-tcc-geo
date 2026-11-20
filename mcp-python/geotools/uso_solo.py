"""Tópicos 5.3 e 5.6 do plano: classes de uso e cobertura da terra dentro de um polígono."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.mask
from shapely.geometry import box

from .catalogo import Catalogo
from .erros import ErroGeo
from .medidas import ha


def uso_solo_na_area(cat: Catalogo, camada: str, feicao: str = "", raster: str = "uso_solo") -> dict:
    """Área (ha) e fração (%) de cada classe de uso do solo dentro da camada ou feição.

    Conta os pixels cujo centro cai no polígono e reparte a área *vetorial* do
    polígono coberta pelo raster pela fração de cada classe; com o raster cobrindo
    tudo, a soma das classes fecha com `calcular_area`, e com cobertura parcial
    sai `aviso_cobertura`.
    """
    meta = cat.meta_raster(raster)
    geom = cat.selecionar(camada, feicao).geometry.union_all()
    if geom.area == 0:
        raise ErroGeo(f"a camada '{camada}' não tem área; uso_solo_na_area só aceita polígonos")
    with rasterio.open(cat.caminho_raster(raster)) as src:
        no_raster = gpd.GeoSeries([geom], crs=cat.epsg).to_crs(src.crs).iloc[0]
        try:
            recorte, _ = rasterio.mask.mask(src, [no_raster], crop=True, filled=False)
        except ValueError as erro:  # polígono fora da extensão do raster
            raise ErroGeo(f"o raster '{raster}' não cobre a área pedida") from erro
        validos = recorte.compressed()
        metodo = "pixels com centro no polígono; área vetorial repartida pela fração de cada classe"
        if validos.size == 0:  # faixa mais estreita que o pixel (estrada, linha de transmissão): nenhum centro cai dentro
            recorte, _ = rasterio.mask.mask(src, [no_raster], crop=True, filled=False, all_touched=True)
            validos = recorte.compressed()
            metodo = "polígono mais estreito que o pixel: pixels que ele toca; área vetorial repartida pela fração de cada classe"
        nomes = {int(k): v for k, v in (meta.get("classes") or {}).items()}
        if src.nodata is None and 0 not in nomes:  # exportação do MapBiomas sem nodata: 0 é o fundo, não uma classe
            validos = validos[validos != 0]
        # shortcut: só a extensão do raster conta como cobertura; buracos de nodata dentro dela ainda são repartidos
        extensao = gpd.GeoSeries([box(*src.bounds)], crs=src.crs).to_crs(cat.epsg).iloc[0]
        resolucao = [abs(float(v)) for v in src.res]
        crs_raster = src.crs.to_string()
    coberta = geom.intersection(extensao).area
    cobertura = round(100 * coberta / geom.area, 2)
    if validos.size == 0 or coberta == 0:
        raise ErroGeo(f"o raster '{raster}' não cobre a área pedida")
    codigos, contagens = np.unique(validos, return_counts=True)
    classes = [
        {
            "codigo": int(c),
            "classe": nomes.get(int(c), f"classe {int(c)}"),
            "pixels": int(n),
            "area_ha": ha(coberta * n / validos.size),
            "percentual": round(100 * n / validos.size, 2),
        }
        for c, n in sorted(zip(codigos, contagens), key=lambda par: -par[1])
    ]
    return {
        "status": "sucesso",
        "ferramenta": "uso_solo_na_area",
        "camada": camada,
        "feicao": feicao or None,
        "raster": raster,
        "classes": classes,
        "area_total_ha": ha(geom.area),
        "area_coberta_pelo_raster_ha": ha(coberta),
        "cobertura_do_raster_pct": cobertura,
        **({"aviso_cobertura": f"o raster cobre só {cobertura} % da área: as classes somam a área coberta, o resto fica sem dado"}
           if cobertura < 99.5 else {}),
        "pixels_contados": int(validos.size),
        "resolucao_do_raster": resolucao,
        "crs_do_raster": crs_raster,
        "metodo": metodo,
        **cat.procedencia(camada, raster),
    }
