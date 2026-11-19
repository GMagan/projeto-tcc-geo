"""Fixtures dos testes.

`cat` é um catálogo sintético: uma "UC" retangular de 2.000 m x 1.000 m em
SIRGAS 2000 / UTM 22S, com zonas, municípios, estrada e raster de uso do solo
de tamanhos escolhidos para que toda resposta esperada saia de conta de cabeça.
Assim cada teste compara a tool com a geometria analítica, e não com ela mesma.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import yaml
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point, Polygon, box

RAIZ = Path(__file__).resolve().parents[1]
E0, N0 = 400_000.0, 7_160_000.0  # canto sudoeste da UC sintética
UTM, GEO = 31982, 4674


@pytest.fixture(scope="session")
def pasta_sintetica(tmp_path_factory) -> Path:
    pasta = tmp_path_factory.mktemp("dados")
    gpkg = pasta / "base.gpkg"

    def gravar(camada: str, linhas: list[dict], crs_final: int = UTM) -> None:
        gdf = gpd.GeoDataFrame(linhas, geometry="geometry", crs=UTM).to_crs(crs_final)
        gdf.to_file(gpkg, layer=camada, driver="GPKG")

    uc = box(E0, N0, E0 + 2000, N0 + 1000)  # 200 ha, perímetro 6 km
    gravar("limite_uc", [{"nome": "UC Sintética", "geometry": uc}], crs_final=GEO)  # gravada em graus de propósito
    gravar(
        "zoneamento",
        [
            {"sigla": "ZC", "zona": "Zona de Conservação", "geometry": box(E0, N0, E0 + 1500, N0 + 1000)},  # 150 ha
            {"sigla": "ZAA", "zona": "Zona de Adequação Ambiental", "geometry": box(E0 + 1500, N0, E0 + 1900, N0 + 1000)},  # 40 ha
            {"sigla": "ZI", "zona": "Zona de Infraestrutura", "geometry": box(E0 + 1900, N0, E0 + 2000, N0 + 500)},  # 5 ha
            {"sigla": "ZDIP", "zona": "Zona de Diferentes Interesses Públicos", "geometry": box(E0 + 1900, N0 + 500, E0 + 2000, N0 + 1000)},  # 5 ha
        ],
    )
    gravar(
        "zona_amortecimento",
        [{"sigla": "ZA", "zona": "Zona de Amortecimento", "geometry": uc.buffer(500, quad_segs=64).difference(uc)}],
    )
    gravar(
        "municipios",
        [
            {"nome": "Alfa", "geometry": box(E0 - 5000, N0 - 5000, E0 + 1000, N0 + 5000)},  # metade oeste da UC
            {"nome": "Beta", "geometry": box(E0 + 1000, N0 - 5000, E0 + 7000, N0 + 5000)},  # metade leste
        ],
    )
    gravar("rodovias", [{"nome": "PR-000", "geometry": LineString([(E0 - 1000, N0 + 500), (E0 + 3000, N0 + 500)])}])
    gravar(
        "estruturas",
        [
            {"nome": "Posto", "geometry": Point(E0 + 100, N0 + 100)},  # dentro da UC
            {"nome": "Mirante", "geometry": Point(E0 + 2250, N0 + 500)},  # 250 m a leste da UC
        ],
    )
    gravar("invalida", [{"nome": "laço", "geometry": Polygon([(0, 0), (100, 100), (100, 0), (0, 100)])}])
    gravar("marco", [{"nome": "equador no meridiano central", "geometry": Point(500_000, 10_000_000)}], crs_final=GEO)

    # raster de 10 m: classe 10 (floresta) a oeste de E0+1000, classe 40 (lavoura) a leste
    transform = from_origin(E0 - 100, N0 + 1100, 10, 10)
    dados = np.full((120, 220), 10, dtype=np.uint8)
    dados[:, 110:] = 40
    with rasterio.open(
        pasta / "uso.tif", "w", driver="GTiff", height=120, width=220, count=1,
        dtype="uint8", crs=f"EPSG:{UTM}", transform=transform, nodata=0,
    ) as dst:
        dst.write(dados, 1)

    def camada(nome: str, **extra) -> dict:
        return {"arquivo": "base.gpkg", "camada": nome, "descricao": f"camada sintética {nome}",
                "fonte": "sintética", "licenca": "n/a", "provisorio": False, **extra}

    catalogo = {
        "crs_trabalho": UTM,
        "uc": {"nome": "UC Sintética", "sigla": "UCS"},
        "camadas": {
            "limite_uc": camada("limite_uc", campo_nome="nome"),
            "zoneamento": camada("zoneamento", campo_sigla="sigla", campo_nome="zona", provisorio=True),
            "zona_amortecimento": camada("zona_amortecimento", campo_sigla="sigla", campo_nome="zona"),
            "municipios": camada("municipios", campo_nome="nome"),
            "rodovias": camada("rodovias", campo_nome="nome"),
            "estruturas": camada("estruturas", campo_nome="nome"),
            "invalida": camada("invalida", campo_nome="nome"),
            "marco": camada("marco", campo_nome="nome"),
        },
        "rasters": {
            "uso_solo": {"arquivo": "uso.tif", "descricao": "raster sintético", "fonte": "sintética",
                         "licenca": "n/a", "provisorio": False, "classes": {10: "Cobertura arbórea", 40: "Lavoura"}},
        },
    }
    (pasta / "catalogo.yaml").write_text(yaml.safe_dump(catalogo, allow_unicode=True), encoding="utf-8")
    return pasta


@pytest.fixture(scope="session")
def cat(pasta_sintetica):
    from geotools import Catalogo

    return Catalogo(pasta_sintetica / "catalogo.yaml")


def lonlat(e: float, n: float) -> tuple[float, float]:
    """Converte UTM 22S em lon/lat SIRGAS 2000 (usado só para montar entradas de teste)."""
    from pyproj import Transformer

    return Transformer.from_crs(UTM, GEO, always_xy=True).transform(e, n)
