"""Tópicos 5.4 a 5.6 do plano: distância, interseção e faixas (buffer)."""
from __future__ import annotations

import geopandas as gpd
import shapely
from pyproj import CRS
from shapely.geometry import Point

from .catalogo import Catalogo
from .erros import ErroGeo
from .medidas import EPSG_GEOGRAFICO, GEOD, ha, km


def distancia_ate(
    cat: Catalogo, camada_origem: str, camada_destino: str, feicao_origem: str = "", feicao_destino: str = ""
) -> dict:
    """Menor distância (m) da origem até cada feição da camada de destino."""
    origem = cat.selecionar(camada_origem, feicao_origem).geometry.union_all()
    destino = cat.selecionar(camada_destino, feicao_destino)
    if destino.empty:
        raise ErroGeo(f"a camada '{camada_destino}' não tem feições para medir a distância")
    campo = cat.meta(camada_destino).get("campo_sigla") or cat.meta(camada_destino).get("campo_nome")
    feicoes = [
        {"feicao": str(linha[campo]) if campo and campo in destino and linha[campo] else f"feição {i}",
         "distancia_m": round(float(origem.distance(linha.geometry)), 2)}
        for i, (_, linha) in enumerate(destino.iterrows())
    ]
    feicoes.sort(key=lambda f: f["distancia_m"])
    return {
        "status": "sucesso",
        "ferramenta": "distancia_ate",
        "origem": {"camada": camada_origem, "feicao": feicao_origem or None},
        "destino": {"camada": camada_destino, "feicao": feicao_destino or None},
        "distancia_minima_m": feicoes[0]["distancia_m"],
        "feicoes": feicoes[:20],
        "n_feicoes_destino": len(feicoes),
        "crs_calculo": cat.crs,
        **cat.procedencia(camada_origem, camada_destino),
    }


def _dimensao(geom) -> int:
    """0 ponto, 1 linha, 2 polígono; coleção mista (rios + nascentes) vale a maior."""
    return int(shapely.get_dimensions(geom))


def intersecao(cat: Catalogo, camada_a: str, camada_b: str, feicao_a: str = "", feicao_b: str = "") -> dict:
    """Parte comum entre A e B: área (polígonos), comprimento (linhas) ou contagem (pontos)."""
    a = cat.selecionar(camada_a, feicao_a).geometry.union_all()
    b = cat.selecionar(camada_b, feicao_b).geometry.union_all()
    for nome, geom in ((camada_a, a), (camada_b, b)):
        if geom.is_empty:
            raise ErroGeo(f"a camada '{nome}' não tem feições para a interseção")
    comum = a.intersection(b)
    saida = {
        "status": "sucesso",
        "ferramenta": "intersecao",
        "a": {"camada": camada_a, "feicao": feicao_a or None},
        "b": {"camada": camada_b, "feicao": feicao_b or None},
    }
    dim = min(_dimensao(a), _dimensao(b))
    if dim == 2:
        saida["area_intersecao_ha"] = ha(comum.area)
        saida["percentual_de_a"] = round(100 * comum.area / a.area, 2)
        saida["percentual_de_b"] = round(100 * comum.area / b.area, 2)
    elif dim == 1:
        linha = a if _dimensao(a) == 1 else b
        saida["comprimento_intersecao_km"] = km(comum.length)
        saida["percentual_do_comprimento"] = round(100 * comum.length / linha.length, 2)
    else:
        saida["n_pontos_na_intersecao"] = 0 if comum.is_empty else len(getattr(comum, "geoms", [comum]))
    return {**saida, "crs_calculo": cat.crs, **cat.procedencia(camada_a, camada_b)}


def calcular_buffer(cat: Catalogo, camada: str, distancia_m: float, feicao: str = "") -> dict:
    """Faixa de `distancia_m` metros em volta da camada (ex.: entorno de 3 km da UC)."""
    if distancia_m <= 0:
        raise ErroGeo("distancia_m deve ser maior que zero (em metros)")
    geom = cat.selecionar(camada, feicao).geometry.union_all()
    ampliado = geom.buffer(distancia_m, quad_segs=128)
    return {
        "status": "sucesso",
        "ferramenta": "calcular_buffer",
        "camada": camada,
        "feicao": feicao or None,
        "distancia_m": float(distancia_m),
        "area_original_ha": ha(geom.area),
        "area_buffer_ha": ha(ampliado.area),
        "area_faixa_ha": ha(ampliado.area - geom.area),
        "perimetro_buffer_km": km(ampliado.length),
        "crs_calculo": cat.crs,
        "metodo": "buffer euclidiano no CRS de trabalho (UTM), em metros",
        **cat.procedencia(camada),
    }


def buffer_geodesico(lon: float, lat: float, raio_m: float):
    """Círculo de raio `raio_m` medido sobre o elipsoide, em lon/lat SIRGAS 2000.

    Usa a projeção azimutal equidistante centrada no ponto, na qual a distância
    ao centro é exata. (No Web Mercator, EPSG:3857, o mesmo "raio" encolhe no
    terreno pelo cosseno da latitude.)
    """
    local = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +ellps=GRS80 +units=m +no_defs")
    circulo = Point(0, 0).buffer(raio_m, quad_segs=256)
    return gpd.GeoSeries([circulo], crs=local).to_crs(EPSG_GEOGRAFICO).iloc[0]


def calcular_buffer_coordenada(lon: float, lat: float, raio_metros: float) -> dict:
    """Área de influência circular em volta de uma coordenada (graus decimais)."""
    if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
        raise ErroGeo(f"coordenada impossível (lon={lon}, lat={lat})")
    if raio_metros <= 0:
        raise ErroGeo("raio_metros deve ser maior que zero")
    area, perimetro = GEOD.geometry_area_perimeter(buffer_geodesico(lon, lat, raio_metros))
    return {
        "status": "sucesso",
        "ferramenta": "calcular_buffer_coordenada",
        "lon": lon,
        "lat": lat,
        "raio_aplicado_m": float(raio_metros),
        "area_total_ha": ha(abs(area)),
        "perimetro_km": km(perimetro),
        "sistema_projecao_utilizado": "Azimutal equidistante centrada no ponto, elipsoide GRS80 (SIRGAS 2000)",
        "metodo": "círculo geodésico; área medida sobre o elipsoide",
    }
