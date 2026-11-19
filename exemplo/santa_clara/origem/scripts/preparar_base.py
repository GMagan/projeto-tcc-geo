#!/usr/bin/env python3
"""Monta a base cartográfica do projeto em SIRGAS 2000 / UTM 22S (EPSG:31982).

Lê os dados brutos (scripts/baixar_dados.py) e o zoneamento vetorizado
(scripts/vetorizar_zoneamento.py) e grava dados/processados/base.gpkg com as
camadas descritas em dados/catalogo.yaml. É a tarefa 1.2 (Base cartográfica)
do plano: carregar, validar e reprojetar.

Uso:  python scripts/preparar_base.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import rasterio
import rasterio.mask
from shapely import make_valid
from shapely.geometry import LineString, Point, Polygon, box

RAIZ = Path(__file__).resolve().parents[1]
BRUTOS = RAIZ / "dados" / "brutos"
PROC = RAIZ / "dados" / "processados"
BASE = PROC / "base.gpkg"
EPSG = 31982
CODIGO_CNUC_PESC = 2259  # Parque Estadual de Santa Clara no CNUC


def gravar(gdf: gpd.GeoDataFrame, camada: str) -> None:
    gdf = gdf.to_crs(EPSG)
    gdf["geometry"] = gdf.geometry.apply(make_valid)
    gdf.to_file(BASE, layer=camada, driver="GPKG")
    print(f"  {camada:22s} {len(gdf):4d} feições  {gdf.geom_type.unique().tolist()}")


def limite_decreto() -> gpd.GeoDataFrame:
    ucs = gpd.read_file(BRUTOS / "geobr_ucs" / "conservation_units_201909.gpkg")
    uc = ucs[ucs["code_conservation_unit"].astype(float) == CODIGO_CNUC_PESC]
    if len(uc) != 1:
        raise RuntimeError("PESC não encontrado no CNUC")
    linha = uc.iloc[0]
    return gpd.GeoDataFrame(
        [
            {
                "nome": "Parque Estadual de Santa Clara",
                "sigla": "PESC",
                "ato_legal": linha["legislation"],
                "codigo_cnuc": linha["code_u111"],
                "fonte": "CNUC/MMA (set. 2019) via geobr/IPEA: polígono do memorial descritivo do decreto",
                "provisorio": False,
            }
        ],
        geometry=[linha.geometry],
        crs=ucs.crs,
    )


def municipios(area_de_interesse) -> gpd.GeoDataFrame:
    malha = gpd.read_file(BRUTOS / "ibge_municipios_pr" / "PR_Municipios_2024.zip").to_crs(EPSG)
    perto = malha[malha.intersects(area_de_interesse)]
    return gpd.GeoDataFrame(
        {
            "nome": perto["NM_MUN"].values,
            "codigo_ibge": perto["CD_MUN"].values,
            "fonte": "IBGE, Malha Municipal 2024 (1:250.000)",
            "provisorio": False,
        },
        geometry=perto.geometry.values,
        crs=EPSG,
    )


def camadas_osm() -> dict[str, gpd.GeoDataFrame]:
    dados = json.loads((BRUTOS / "osm" / "overpass_pesc.json").read_text(encoding="utf-8"))
    fonte = f"OpenStreetMap (base de {dados['osm3s']['timestamp_osm_base'][:10]}), ODbL"
    vias, agua_linha, agua_area, edificacoes, energia, pontos = [], [], [], [], [], []
    for el in dados["elements"]:
        tags = el.get("tags", {})
        comum = {"osm_id": el["id"], "nome": tags.get("name") or tags.get("ref") or "", "fonte": fonte, "provisorio": False}
        if el["type"] == "node":
            pontos.append({**comum, "tipo": tags.get("tourism", ""), "geometry": Point(el["lon"], el["lat"])})
            continue
        if el["type"] != "way" or "geometry" not in el:
            continue
        coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
        fechado = len(coords) >= 4 and coords[0] == coords[-1]
        if "highway" in tags:
            vias.append({**comum, "tipo": tags["highway"], "ref": tags.get("ref", ""), "geometry": LineString(coords)})
        elif "building" in tags and fechado:
            edificacoes.append({**comum, "tipo": tags["building"], "geometry": Polygon(coords)})
        elif tags.get("natural") == "water" and fechado:
            agua_area.append({**comum, "tipo": tags.get("water", "water"), "geometry": Polygon(coords)})
        elif "waterway" in tags:
            agua_linha.append({**comum, "tipo": tags["waterway"], "geometry": LineString(coords)})
        elif tags.get("power") == "line":
            energia.append({**comum, "tipo": "linha de transmissão", "geometry": LineString(coords)})

    def gdf(linhas):
        return gpd.GeoDataFrame(linhas, geometry="geometry", crs=4326)

    return {
        "rodovias": gdf(vias),
        "hidrografia": gdf(agua_linha),
        "massas_dagua": gdf(agua_area),
        "edificacoes": gdf(edificacoes),
        "linhas_transmissao": gdf(energia),
        "estruturas": gdf(pontos),
    }


def recortar_uso_do_solo(area_de_interesse) -> None:
    origem = BRUTOS / "esa_worldcover" / "ESA_WorldCover_10m_2021_v200_S27W054_Map.tif"
    destino = PROC / "uso_solo_worldcover_2021.tif"
    janela = gpd.GeoSeries([area_de_interesse], crs=EPSG).to_crs(4326).iloc[0]
    with rasterio.open(origem) as src:
        dados, transform = rasterio.mask.mask(src, [janela], crop=True, nodata=0)
        perfil = src.profile.copy()
        perfil.update(height=dados.shape[1], width=dados.shape[2], transform=transform, compress="deflate", nodata=0)
        with rasterio.open(destino, "w", **perfil) as dst:
            dst.write(dados)
    print(f"  uso_solo (raster)      {dados.shape[2]}x{dados.shape[1]} pixels  {destino.name}")


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    BASE.unlink(missing_ok=True)
    print(f"gravando {BASE.relative_to(RAIZ)} em EPSG:{EPSG}")

    vetorizado = PROC / "vetorizacao" / "zoneamento_vetorizado.gpkg"
    za = None
    for camada in ("limite_uc", "zoneamento", "zona_amortecimento"):
        gdf = gpd.read_file(vetorizado, layer=camada)
        gravar(gdf, camada)
        if camada == "zona_amortecimento":
            za = gdf.geometry.union_all()

    decreto = limite_decreto()
    gravar(decreto, "limite_decreto")

    # área de interesse: retângulo envolvente da ZA e do limite do decreto, com 2 km de folga
    xmin, ymin, xmax, ymax = za.union(decreto.to_crs(EPSG).geometry.iloc[0]).bounds
    interesse = box(xmin - 2000, ymin - 2000, xmax + 2000, ymax + 2000)

    gravar(municipios(interesse), "municipios")
    for nome, gdf in camadas_osm().items():
        gdf = gdf.to_crs(EPSG)
        gravar(gdf[gdf.intersects(interesse)].copy(), nome)
    recortar_uso_do_solo(interesse)


if __name__ == "__main__":
    main()
