"""Tópicos 5.1 a 5.5 do plano: zoneamento interno da UC."""
from __future__ import annotations

from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import nearest_points

from .catalogo import Catalogo
from .erros import ErroGeo
from .medidas import EPSG_GEOGRAFICO, GEOD, ha, para_geografico

LONGE_M = 50_000  # além disso, a coordenada provavelmente foi digitada errada


def _tabela_de_zonas(cat: Catalogo) -> tuple[list[dict], float, float]:
    """Linhas (sigla, zona, área em m²), área da união e soma das áreas."""
    meta = cat.meta("zoneamento")
    gdf = cat.ler("zoneamento")
    campo_sigla, campo_nome = meta.get("campo_sigla", "sigla"), meta.get("campo_nome", "zona")
    linhas = [
        {"sigla": str(sigla), "zona": str(grupo[campo_nome].iloc[0]), "area_m2": float(grupo.geometry.union_all().area)}
        for sigla, grupo in gdf.groupby(campo_sigla, sort=False)
    ]
    return linhas, float(gdf.geometry.union_all().area), sum(l["area_m2"] for l in linhas)


def calcular_area_zonas(cat: Catalogo) -> dict:
    """Tabela de áreas (ha) por zona, total e conferência com o limite da UC."""
    linhas, area_uniao, soma = _tabela_de_zonas(cat)
    area_limite = float(cat.ler("limite_uc").geometry.union_all().area)
    saida = {
        "status": "sucesso",
        "ferramenta": "calcular_area_zonas",
        "zonas": [{"sigla": l["sigla"], "zona": l["zona"], "area_ha": ha(l["area_m2"])} for l in linhas],
        "total_ha": ha(soma),
        "area_limite_uc_ha": ha(area_limite),
        "diferenca_para_o_limite_ha": ha(soma - area_limite),
        "sobreposicao_entre_zonas_ha": ha(soma - area_uniao),
        "crs_calculo": cat.crs,
    }
    camadas = ["zoneamento", "limite_uc"]
    if "zona_amortecimento" in cat.camadas:
        saida["zona_amortecimento_ha"] = ha(cat.ler("zona_amortecimento").geometry.union_all().area)
        saida["observacao"] = "a zona de amortecimento fica fora da UC e não entra no total"
        camadas.append("zona_amortecimento")
    return {**saida, **cat.procedencia(*camadas)}


def percentual_por_zona(cat: Catalogo) -> dict:
    """Participação (%) de cada zona na área total zoneada da UC."""
    linhas, _, soma = _tabela_de_zonas(cat)
    return {
        "status": "sucesso",
        "ferramenta": "percentual_por_zona",
        "zonas": [
            {"sigla": l["sigla"], "zona": l["zona"], "area_ha": ha(l["area_m2"]), "percentual": round(100 * l["area_m2"] / soma, 2)}
            for l in linhas
        ],
        "total_ha": ha(soma),
        "soma_percentual": round(sum(100 * l["area_m2"] / soma for l in linhas), 2),
        "crs_calculo": cat.crs,
        **cat.procedencia("zoneamento"),
    }


def zona_da_coordenada(cat: Catalogo, lon: float, lat: float) -> dict:
    """Em que zona cai o ponto (lon, lat) em graus decimais SIRGAS 2000."""
    if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
        raise ErroGeo(f"coordenada impossível (lon={lon}, lat={lat}): use graus decimais, lon entre -180 e 180 e lat entre -90 e 90")
    limite = cat.ler("limite_uc").geometry.union_all()
    centro = para_geografico(limite.centroid, cat.epsg)
    # distância à borda, não ao centro: UC da Amazônia tem centenas de km de lado
    perto = nearest_points(para_geografico(limite, cat.epsg), Point(lon, lat))[0]
    afastamento = GEOD.inv(lon, lat, perto.x, perto.y)[2]
    saida = {
        "status": "sucesso",
        "ferramenta": "zona_da_coordenada",
        "lon": lon,
        "lat": lat,
        "utm_e": None,
        "utm_n": None,
        "dentro_da_uc": False,
        "sigla": None,
        "zona": None,
        "dentro_da_zona_de_amortecimento": False,
        "distancia_ao_limite_da_uc_m": None,  # longe demais: só o aviso, com a distância ao centro
        "aviso": None,
        "crs_calculo": cat.crs,
    }
    if afastamento > LONGE_M:
        saida["aviso"] = (
            f"ponto a {afastamento / 1000:.0f} km da UC: confira se lon e lat não foram trocados "
            f"(nesta UC, lon fica perto de {centro.x:.2f} e lat perto de {centro.y:.2f})"
        )
        return saida

    e, n = Transformer.from_crs(EPSG_GEOGRAFICO, cat.epsg, always_xy=True).transform(lon, lat)
    ponto = Point(e, n)
    saida.update(utm_e=round(e, 2), utm_n=round(n, 2))
    saida["dentro_da_uc"] = bool(limite.covers(ponto))
    saida["distancia_ao_limite_da_uc_m"] = round(float(limite.boundary.distance(ponto)), 2)

    meta = cat.meta("zoneamento")
    zonas = cat.ler("zoneamento")
    achadas = zonas[zonas.covers(ponto)]
    if len(achadas):
        saida["sigla"] = str(achadas.iloc[0][meta.get("campo_sigla", "sigla")])
        saida["zona"] = str(achadas.iloc[0][meta.get("campo_nome", "zona")])
    camadas = ["limite_uc", "zoneamento"]
    if "zona_amortecimento" in cat.camadas:
        saida["dentro_da_zona_de_amortecimento"] = bool(cat.ler("zona_amortecimento").covers(ponto).any())
        camadas.append("zona_amortecimento")
    return {**saida, **{k: v for k, v in cat.procedencia(*camadas).items() if k != "aviso" or not saida["aviso"]}}
