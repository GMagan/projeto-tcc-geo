"""Tópico 3.1 do plano: medidas da ficha técnica (área, perímetro, extremos, municípios)."""
from __future__ import annotations

import geopandas as gpd
import shapely
from pyproj import Geod

from .catalogo import Catalogo

EPSG_GEOGRAFICO = 4674  # SIRGAS 2000, coordenadas geográficas
GEOD = Geod(ellps="GRS80")  # elipsoide do SIRGAS 2000


def ha(m2: float) -> float:
    return round(float(m2) / 1e4, 2)


def km(m: float) -> float:
    return round(float(m) / 1e3, 2)


def para_geografico(geom, epsg_origem: int):
    return gpd.GeoSeries([geom], crs=epsg_origem).to_crs(EPSG_GEOGRAFICO).iloc[0]


def area_geodesica_m2(geom, epsg_origem: int) -> float:
    """Área sobre o elipsoide GRS80 (independe de projeção)."""
    densa = shapely.segmentize(geom, 100.0)  # lados retos no UTM não são geodésicas
    return abs(GEOD.geometry_area_perimeter(para_geografico(densa, epsg_origem))[0])


def calcular_area(cat: Catalogo, camada: str, feicao: str = "") -> dict:
    """Área (ha) e perímetro (km) da camada inteira ou de uma feição dela.

    O valor principal é a área plana em SIRGAS 2000 / UTM, convenção que
    reproduz a área do decreto da UC; a área elipsoidal vai junto para auditoria.
    """
    gdf = cat.selecionar(camada, feicao)
    geom = gdf.geometry.union_all()
    return {
        "status": "sucesso",
        "ferramenta": "calcular_area",
        "camada": camada,
        "feicao": feicao or None,
        "n_feicoes": len(gdf),
        "area_ha": ha(geom.area),
        "perimetro_km": km(geom.length),
        "area_m2": round(float(geom.area), 2),
        "area_geodesica_ha": round(area_geodesica_m2(geom, cat.epsg) / 1e4, 4),
        "crs_calculo": cat.crs,
        "metodo": "área plana no CRS de trabalho; área geodésica no elipsoide GRS80",
        **cat.procedencia(camada),
    }


def graus_para_gms(valor: float) -> str:
    """Graus decimais -> graus, minutos e segundos, no formato da ficha técnica: 51° 58' 14,456\\"."""
    total = round(abs(valor) * 3600, 3)
    graus, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{int(graus)}° {int(minutos)}' {segundos:.3f}\"".replace(".", ",")


def coordenadas_extremas(cat: Catalogo, camada: str, feicao: str = "") -> dict:
    """Vértices mais ao norte, sul, leste e oeste, em SIRGAS 2000 geográfico."""
    geom = para_geografico(cat.selecionar(camada, feicao).geometry.union_all(), cat.epsg)
    vertices = shapely.get_coordinates(geom)
    escolhas = {
        "norte": vertices[vertices[:, 1].argmax()],
        "sul": vertices[vertices[:, 1].argmin()],
        "leste": vertices[vertices[:, 0].argmax()],
        "oeste": vertices[vertices[:, 0].argmin()],
    }
    extremos = {}
    for nome, (lon, lat) in escolhas.items():
        lon, lat = round(float(lon), 7), round(float(lat), 7)
        # norte e sul são definidos pela latitude; leste e oeste, pela longitude
        definidora = f"{graus_para_gms(lat)} S" if nome in ("norte", "sul") else f"{graus_para_gms(lon)} O"
        extremos[nome] = {
            "lon": lon,
            "lat": lat,
            "gms": f"{graus_para_gms(lon)} / {graus_para_gms(lat)}",
            "coordenada_extrema": definidora,
        }
    return {
        "status": "sucesso",
        "ferramenta": "coordenadas_extremas",
        "camada": camada,
        **extremos,
        "formato_gms": "longitude oeste / latitude sul",
        "crs": f"EPSG:{EPSG_GEOGRAFICO} (SIRGAS 2000)",
        **cat.procedencia(camada),
    }


def municipios_intersectados(cat: Catalogo, camada: str = "limite_uc", camada_municipios: str = "municipios") -> dict:
    """Municípios que a camada toca, com a área (ha) e a fração (%) em cada um."""
    alvo = cat.ler(camada).geometry.union_all()
    campo = cat.meta(camada_municipios).get("campo_nome", "nome")
    linhas = []
    for _, mun in cat.ler(camada_municipios).iterrows():
        parte = alvo.intersection(mun.geometry).area
        if parte > 0:
            linhas.append({"municipio": mun[campo], "area_ha": ha(parte), "percentual": round(100 * parte / alvo.area, 2)})
    linhas.sort(key=lambda m: -m["area_ha"])
    coberta = sum(alvo.intersection(g).area for g in cat.ler(camada_municipios).geometry)
    return {
        "status": "sucesso",
        "ferramenta": "municipios_intersectados",
        "camada": camada,
        "municipios": linhas,
        "area_total_ha": ha(alvo.area),
        "area_fora_da_malha_ha": ha(max(alvo.area - coberta, 0.0)),
        "crs_calculo": cat.crs,
        **cat.procedencia(camada, camada_municipios),
    }
