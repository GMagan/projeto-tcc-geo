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


def test_sigla_errada_em_zonas_yaml_para_em_vez_de_sumir_com_a_zona(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada, [{"NOME_ZONA": "Uso público", "geometry": box(E0, N0 - 100, E0 + 100, N0)}])
    (entrada / "zonas.yaml").write_text("Uso público: ZUP\n", encoding="utf-8")
    with pytest.raises(ErroImportacao, match="ZUP"):
        importar(pasta)


def test_camada_com_texto_de_zona_no_atributo_nao_vira_zoneamento(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada)
    gravar(entrada, "app", [{"tipo": "Área de Preservação Permanente", "geometry": box(E0, N0 - 500, E0 + 500, N0)}])
    importar(pasta)
    cat = gt.Catalogo(pasta / "catalogo.yaml")
    assert {z["sigla"]: z["area_ha"] for z in gt.calcular_area_zonas(cat)["zonas"]}["ZP"] == 100.0
    assert "app" in cat.camadas


def test_uc_ao_norte_do_equador_sai_com_n_e_nao_s(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    # Amapá: UTM 22 norte (EPSG 31976), cerca de 2,7° N
    gpd.GeoDataFrame({"zona": ["Zona de Preservação"]}, geometry=[box(400_000, 300_000, 402_000, 301_000)],
                     crs=31976).to_file(entrada / "zoneamento.gpkg")
    importar(pasta)
    r = gt.coordenadas_extremas(gt.Catalogo(pasta / "catalogo.yaml"), "limite_uc")
    assert r["norte"]["lat"] > 0 and r["norte"]["coordenada_extrema"].endswith(" N")
    assert r["oeste"]["coordenada_extrema"].endswith(" O")


def test_raster_sem_nome_de_uso_do_solo_e_ignorado_com_aviso(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada)
    with rasterio.open(entrada / "altitude.tif", "w", driver="GTiff", height=10, width=10, count=1, dtype="uint16",
                       crs=f"EPSG:{EPSG}", transform=from_origin(E0, N0 + 1000, 200, 100)) as r:
        r.write(np.full((1, 10, 10), 812, dtype=np.uint16))
    rel = importar(pasta)
    assert rel["rasters"] == [] and any("altitude.tif ignorado" in a for a in rel["avisos"])


def test_mapa_de_uc_minuscula_sai_com_barra_de_escala(dados, tmp_path):
    pasta, entrada = dados
    uc_yaml(entrada)
    gravar(entrada, "zoneamento", [{"zona": "Zona de Preservação", "geometry": box(E0, N0, E0 + 30, N0 + 30)}])
    importar(pasta)
    assert gt.gerar_mapa(gt.Catalogo(pasta / "catalogo.yaml"), pasta_saida=tmp_path)["status"] == "sucesso"


def test_limites_municipais_viram_municipios_e_nao_o_limite_da_uc(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada)
    gravar(entrada, "limites_municipais", [{"NM_MUN": "Alfa", "geometry": box(E0 - 9000, N0 - 9000, E0 + 9000, N0 + 9000)}])
    importar(pasta)
    cat = gt.Catalogo(pasta / "catalogo.yaml")
    assert gt.calcular_area(cat, "limite_uc")["area_ha"] == 200.0 and "municipios" in cat.camadas


def test_limite_muito_maior_que_as_zonas_e_avisado(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada)
    gravar(entrada, "limite_za", [{"id": 1, "geometry": UC.buffer(3000)}])
    assert any("sem zona" in a for a in importar(pasta)["avisos"])


def test_geopackage_com_varias_camadas_importa_todas(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    arquivo = entrada / "projeto.gpkg"
    gpd.GeoDataFrame([{"NOME_ZONA": n, "geometry": g} for n, g in ZONAS.items()], crs=EPSG).to_file(arquivo, layer="zonas")
    gpd.GeoDataFrame({"nome": ["rio"]}, geometry=[LineString([(E0, N0 - 10), (E0, N0 + 1010)])], crs=EPSG).to_file(arquivo, layer="hidrografia")
    rel = importar(pasta)
    assert rel["camadas"]["hidrografia"] == "projeto.gpkg/hidrografia" and "zoneamento" in rel["camadas"]


def test_raster_recortado_na_uc_nao_derruba_os_resultados(dados, capsys):
    from scripts.gerar_resultados import uso_solo_por_area
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada, [{"NOME_ZONA": "Zona de Amortecimento", "geometry": UC.buffer(500)}])
    with rasterio.open(entrada / "uso.tif", "w", driver="GTiff", height=100, width=200, count=1, dtype="uint8",
                       crs=f"EPSG:{EPSG}", transform=from_origin(E0, N0 + 1000, 10, 10), nodata=0) as r:
        r.write(np.full((1, 100, 200), 3, dtype=np.uint8))  # só a UC: fora dela é "sem dado"
    importar(pasta)
    cat = gt.Catalogo(pasta / "catalogo.yaml")
    uso = uso_solo_por_area(cat, {"UC": ("limite_uc", ""), "ZA": ("zona_amortecimento", "")})
    assert list(uso) == ["UC"] and "ZA sem uso do solo" in capsys.readouterr().out


def test_feicao_sem_nome_de_zona_e_avisada_com_a_area_que_ficou_de_fora(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada, [{"NOME_ZONA": None, "geometry": box(E0, N0 - 1000, E0 + 1000, N0)}])  # 100 ha sem zona
    assert any("1 feição(ões)" in a and "100.00 ha" in a for a in importar(pasta)["avisos"])


def test_legenda_com_ponto_e_virgula_do_excel_em_portugues(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada)
    with rasterio.open(entrada / "uso.tif", "w", driver="GTiff", height=10, width=20, count=1, dtype="uint8",
                       crs=f"EPSG:{EPSG}", transform=from_origin(E0, N0 + 1000, 100, 100)) as r:
        r.write(np.full((1, 10, 20), 3, dtype=np.uint8))
    (entrada / "uso.csv").write_text("codigo;classe\n3;Formação Florestal\n", encoding="cp1252")
    importar(pasta)
    assert gt.Catalogo(pasta / "catalogo.yaml").rasters["uso_solo"]["classes"] == {3: "Formação Florestal"}
    (entrada / "uso.csv").write_text("so uma coluna\n3\n", encoding="utf-8")
    with pytest.raises(ErroImportacao, match="duas colunas"):
        importar(pasta)


@pytest.mark.parametrize("codigos", [[1, 2, 3], [1.0, 2.0, None]])  # com nulo, o shapefile lê a coluna como decimal
def test_zonas_em_codigo_numerico_com_zonas_yaml(dados, codigos):
    pasta, entrada = dados
    uc_yaml(entrada)
    gravar(entrada, "zoneamento", [{"COD_ZONA": c, "geometry": g} for c, g in zip(codigos, ZONAS.values())])
    (entrada / "zonas.yaml").write_text("1: ZP\n2: ZUM\n3: ZI\n", encoding="utf-8")
    importar(pasta)
    siglas = {z["sigla"] for z in gt.calcular_area_zonas(gt.Catalogo(pasta / "catalogo.yaml"))["zonas"]}
    assert siglas == ({"ZP", "ZUM", "ZI"} if None not in codigos else {"ZP", "ZUM"})


def test_zip_com_varios_shapefiles_importa_todos(dados, tmp_path):
    import zipfile
    pasta, entrada = dados
    uc_yaml(entrada)
    soltos = tmp_path / "soltos"
    gravar(soltos, "zoneamento", [{"NOME_ZONA": n, "geometry": g} for n, g in ZONAS.items()], sufixo=".shp")
    gravar(soltos, "hidrografia", [{"nome": "rio", "geometry": LineString([(E0, N0 - 10), (E0, N0 + 1010)])}], sufixo=".shp")
    with zipfile.ZipFile(entrada / "dados_uc.zip", "w") as z:
        for p in soltos.iterdir():
            z.write(p, p.name)
    rel = importar(pasta)
    assert rel["camadas"]["hidrografia"] == "dados_uc.zip/hidrografia" and rel["camadas"]["zoneamento"] == "dados_uc.zip/zoneamento"


def test_mesmo_nome_em_subpastas_diferentes_nao_some(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada)
    for sub in ("estaduais", "municipais"):
        gravar(entrada / sub, "estradas", [{"nome": sub, "geometry": LineString([(E0, N0), (E0 + 500, N0 + 500)])}])
    rel = importar(pasta)
    assert {"estradas", "municipais_estradas"} <= set(rel["camadas"])
    assert any("municipais_estradas" in a for a in rel["avisos"])


def test_interesse_que_nao_e_publico_nao_vira_zdip():
    from scripts.importar_dados import classificar
    assert classificar("Zona de Interesse Histórico-Cultural", {}) is None
    assert classificar("Zona de Diferentes Interesses Públicos", {}) == "ZDIP"


def test_fuso_sem_codigo_sirgas_2000_para_em_vez_de_usar_outro_datum():
    from scripts.importar_dados import epsg_utm
    assert epsg_utm(-60.02, -3.1) == 31980  # Manaus, 20S
    assert epsg_utm(-60.7, 2.8) == 31974  # Roraima, 20N
    with pytest.raises(ErroImportacao, match="fuso 26S"):
        epsg_utm(-29.3, -20.5)  # Ilha da Trindade


def test_malha_municipal_grande_guarda_so_os_vizinhos(dados):
    pasta, entrada = dados
    uc_yaml(entrada)
    zonas(entrada)
    gravar(entrada, "municipios", [{"NM_MUN": "Alfa", "geometry": box(E0 - 9000, N0 - 9000, E0 + 9000, N0 + 9000)},
                                   {"NM_MUN": "Longe", "geometry": box(E0 + 200_000, N0, E0 + 201_000, N0 + 1000)}])
    importar(pasta)
    cat = gt.Catalogo(pasta / "catalogo.yaml")
    assert cat.rotulos("municipios") == ["Alfa"]
