"""Testes do importador (scripts/importar_dados.py).

Tudo vem do usuário: o importador não pode completar nada com dado de outro lugar.
O que falta, ele pergunta (nome da UC, zona desconhecida) ou avisa (camada ausente).
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import yaml
from rasterio.transform import from_origin
from shapely.geometry import LineString, box

import geotools as gt
from scripts.importar_dados import ErroImportacao, importar

# UC sintética de 2.000 m x 1.000 m perto de Manaus (fuso UTM 20 sul, EPSG 31980)
E0, N0, EPSG = 800_000, 9_650_000, 31980
ZONAS = {
    "Zona de Preservação": box(E0, N0, E0 + 1000, N0 + 1000),  # 100 ha
    "ZONA DE USO MODERADO": box(E0 + 1000, N0, E0 + 1800, N0 + 1000),  # 80 ha
    "zona de infraestrutura": box(E0 + 1800, N0, E0 + 2000, N0 + 1000),  # 20 ha
}
UC = box(E0, N0, E0 + 2000, N0 + 1000)


def gravar(pasta, nome, linhas, crs=4674, sufixo=".gpkg"):
    pasta.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(linhas, geometry="geometry", crs=EPSG).to_crs(crs).to_file(pasta / f"{nome}{sufixo}")


def zonas(pasta, extra=None):
    linhas = [{"NOME_ZONA": n, "geometry": g} for n, g in ZONAS.items()] + (extra or [])
    gravar(pasta, "zoneamento_parque", linhas)


def uc_yaml(pasta):
    (pasta / "uc.yaml").write_text("nome: Parque Teste\nsigla: PT\n", encoding="utf-8")


@pytest.fixture
def dados(tmp_path):
    entrada = tmp_path / "dados" / "entrada"
    entrada.mkdir(parents=True)
    return tmp_path / "dados", entrada


def test_dados_completos_viram_catalogo_no_fuso_utm_da_uc(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada, [{"NOME_ZONA": "Zona de Amortecimento", "geometry": UC.buffer(500)}])
    gravar(entrada, "limite_parque", [{"id": 1, "geometry": UC}])
    gravar(entrada, "Municipios_AM", [{"NM_MUN": "Alfa", "geometry": box(E0 - 9000, N0 - 9000, E0 + 1000, N0 + 9000)},
                                      {"NM_MUN": "Beta", "geometry": box(E0 + 1000, N0 - 9000, E0 + 9000, N0 + 9000)}])
    gravar(entrada, "estradas", [{"nome": "AM-010", "geometry": LineString([(E0 - 500, N0 + 500), (E0 + 2500, N0 + 500)])}])
    with rasterio.open(entrada / "uso.tif", "w", driver="GTiff", height=120, width=220, count=1, dtype="uint8",
                       crs=f"EPSG:{EPSG}", transform=from_origin(E0 - 100, N0 + 1100, 10, 10)) as r:
        r.write(np.full((1, 120, 220), 3, dtype=np.uint8))
    (entrada / "uso.csv").write_text("codigo,classe\n3,Floresta\n", encoding="utf-8")
    (entrada / "gabarito.yaml").write_text("area_uc_ha: 200.0\n", encoding="utf-8")

    rel = importar(pasta)

    assert rel["epsg"] == EPSG and rel["faltando"] == []
    cat = gt.Catalogo(pasta / "catalogo.yaml")
    assert cat.uc == {"nome": "Parque Teste", "sigla": "PT"}
    assert {z["sigla"]: z["area_ha"] for z in gt.calcular_area_zonas(cat)["zonas"]} == {"ZP": 100.0, "ZUM": 80.0, "ZI": 20.0}
    assert gt.calcular_area_zonas(cat)["zona_amortecimento_ha"] == pytest.approx(UC.buffer(500).area / 1e4 - 200, abs=0.01)
    assert {m["municipio"]: m["percentual"] for m in gt.municipios_intersectados(cat)["municipios"]} == {"Alfa": 50.0, "Beta": 50.0}
    assert gt.intersecao(cat, "estradas", "limite_uc")["comprimento_intersecao_km"] == 2.0
    assert gt.uso_solo_na_area(cat, "limite_uc")["classes"][0]["classe"] == "Floresta"


def test_so_zoneamento_deriva_o_limite_e_lista_o_que_falta(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada)

    rel = importar(pasta)

    cat = gt.Catalogo(pasta / "catalogo.yaml")
    assert gt.calcular_area(cat, "limite_uc")["area_ha"] == 200.0
    assert any("limite" in a for a in rel["avisos"])
    faltam = " ".join(item for item, _ in rel["faltando"])
    for item in ("zona de amortecimento", "municípios", "uso do solo", "gabarito"):
        assert item in faltam
    assert "municipios" not in cat.camadas  # nada é completado com dado de outro lugar


def test_sem_nome_da_uc_pergunta_e_guarda_a_resposta(dados):
    pasta, entrada = dados
    zonas(entrada)
    with pytest.raises(ErroImportacao, match="uc.yaml"):
        importar(pasta)  # sem terminal para perguntar: explica o que criar

    respostas = iter(["Reserva Nova", "RN"])
    importar(pasta, perguntar=lambda pergunta, opcoes=None: next(respostas))
    assert yaml.safe_load((entrada / "uc.yaml").read_text(encoding="utf-8")) == {"nome": "Reserva Nova", "sigla": "RN"}


def test_zona_desconhecida_e_perguntada_e_a_resposta_fica_salva(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada, [{"NOME_ZONA": "ZPX", "geometry": box(E0, N0 - 100, E0 + 100, N0)}])
    with pytest.raises(ErroImportacao, match="ZPX"):
        importar(pasta)

    importar(pasta, perguntar=lambda pergunta, opcoes=None: "ZC")
    assert yaml.safe_load((entrada / "zonas.yaml").read_text(encoding="utf-8")) == {"ZPX": "ZC"}
    assert "ZC" in gt.Catalogo(pasta / "catalogo.yaml").rotulos("zoneamento")
    importar(pasta)  # já salvo: não pergunta de novo


def test_sem_zoneamento_para_e_pede_o_arquivo(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    gravar(entrada, "limite", [{"id": 1, "geometry": UC}])
    with pytest.raises(ErroImportacao, match="zoneamento"):
        importar(pasta)


def test_shapefile_sem_prj_pede_o_arquivo_que_falta(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    gravar(entrada, "zonas", [{"zona": n, "geometry": g} for n, g in ZONAS.items()], sufixo=".shp")
    (entrada / "zonas.prj").unlink()
    with pytest.raises(ErroImportacao, match=r"\.prj"):
        importar(pasta)


def test_reimportar_tira_camadas_que_o_usuario_removeu(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada)
    gravar(entrada, "estradas", [{"nome": "x", "geometry": LineString([(E0, N0), (E0 + 10, N0)])}])
    importar(pasta)
    (entrada / "estradas.gpkg").unlink()
    importar(pasta)
    assert "estradas" not in gt.Catalogo(pasta / "catalogo.yaml").camadas
