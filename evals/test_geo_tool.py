"""Testes determinísticos das tools espaciais (camada T0).

Cada teste compara a tool com um valor obtido por geometria analítica sobre o
catálogo sintético de `conftest.py`. Nenhum modelo de linguagem participa.
"""
from __future__ import annotations

import math

import pytest
from conftest import E0, N0, lonlat
from pyproj import Geod

import geotools as gt

# --------------------------------------------------------------------------
# 1.2 Base cartográfica: carregar, validar, reprojetar
# --------------------------------------------------------------------------


def test_listar_camadas_devolve_vetores_e_rasters_do_catalogo(cat):
    r = gt.listar_camadas(cat)
    nomes = {c["camada"] for c in r["camadas"]}
    assert {"limite_uc", "zoneamento", "municipios", "uso_solo"} <= nomes


def test_carregar_camada_resume_feicoes_crs_e_procedencia(cat):
    r = gt.carregar_camada(cat, "zoneamento")
    assert r["status"] == "sucesso"
    assert r["n_feicoes"] == 4
    assert r["tipo_geometria"] == ["Polygon"]
    assert r["crs_origem"] == "EPSG:31982"
    assert r["provisorio"] is True
    assert r["fonte"] == "sintética"


def test_carregar_camada_inexistente_diz_quais_existem(cat):
    with pytest.raises(gt.ErroGeo) as erro:
        gt.carregar_camada(cat, "nao_existe")
    assert "limite_uc" in str(erro.value)


def test_validar_geometria_acusa_poligono_em_laco_e_mede_a_correcao(cat):
    r = gt.validar_geometria(cat, "invalida")
    assert r["n_invalidas"] == 1
    assert "Self-intersection" in r["motivos"][0]
    # o laço (0,0)-(100,100)-(100,0)-(0,100) vale dois triângulos de 2.500 m² depois de corrigido
    assert r["area_corrigida_m2"] == pytest.approx(5000.0)


def test_validar_geometria_camada_valida_nao_acusa_nada(cat):
    r = gt.validar_geometria(cat, "zoneamento")
    assert r["n_invalidas"] == 0
    assert r["motivos"] == []


def test_reprojetar_equador_no_meridiano_central_cai_na_origem_do_fuso(cat):
    # por definição do UTM sul: lon = -51 (meridiano central do fuso 22), lat = 0 -> E 500.000, N 10.000.000
    r = gt.reprojetar(cat, "marco", 31982)
    assert r["crs_origem"] == "EPSG:4674"
    assert r["crs_destino"] == "EPSG:31982"
    assert r["extensao_destino"] == pytest.approx([500_000, 10_000_000, 500_000, 10_000_000], abs=1e-3)


# --------------------------------------------------------------------------
# 3.1 Ficha técnica: área, perímetro, extremos, municípios
# --------------------------------------------------------------------------


def test_calcular_area_do_retangulo_de_2000_por_1000_metros(cat):
    r = gt.calcular_area(cat, "limite_uc")
    assert r["area_ha"] == 200.00
    assert r["perimetro_km"] == 6.00
    assert r["crs_calculo"] == "EPSG:31982"


def test_calcular_area_filtra_por_sigla_ou_por_nome_da_zona(cat):
    assert gt.calcular_area(cat, "zoneamento", "ZAA")["area_ha"] == 40.00
    assert gt.calcular_area(cat, "zoneamento", "zona de infraestrutura")["area_ha"] == 5.00


def test_calcular_area_de_feicao_inexistente_diz_quais_existem(cat):
    with pytest.raises(gt.ErroGeo) as erro:
        gt.calcular_area(cat, "zoneamento", "ZX")
    assert "ZC" in str(erro.value)


def test_calcular_area_informa_area_geodesica_coerente_com_o_fator_de_escala_utm(cat):
    # A 99 km do meridiano central o UTM encolhe distâncias por k = k0 (1 + x²/(2 k0² R²)).
    # A área elipsoidal deve ser a área plana dividida por k².
    # x = distância de grade ao meridiano central no centro do retângulo; R = raio médio em 25,67° S
    k0, x, raio = 0.9996, 99_000.0, 6_364_700.0
    k = k0 * (1 + x**2 / (2 * k0**2 * raio**2))
    r = gt.calcular_area(cat, "limite_uc")
    assert r["area_geodesica_ha"] == pytest.approx(200.0 / k**2, rel=2e-6)


def test_formatar_gms_segue_o_formato_da_ficha_tecnica_do_plano():
    # 51,9706822° = 51° 58' 14,456"
    assert gt.graus_para_gms(-51.9706822) == "51° 58' 14,456\""


def test_coordenadas_extremas_apontam_os_vertices_mais_ao_norte_sul_leste_e_oeste(cat):
    r = gt.coordenadas_extremas(cat, "limite_uc")
    # a grade UTM gira em relação aos meridianos, então os extremos são cantos distintos do retângulo
    cantos = [lonlat(E0 + dx, N0 + dy) for dx in (0, 2000) for dy in (0, 1000)]
    assert r["norte"]["lat"] == pytest.approx(max(c[1] for c in cantos), abs=1e-7)
    assert r["sul"]["lat"] == pytest.approx(min(c[1] for c in cantos), abs=1e-7)
    assert r["leste"]["lon"] == pytest.approx(max(c[0] for c in cantos), abs=1e-7)
    assert r["oeste"]["lon"] == pytest.approx(min(c[0] for c in cantos), abs=1e-7)
    assert r["norte"]["gms"].count("°") == 2  # "longitude / latitude", como na Tabela 1 do plano


def test_coordenadas_extremas_destacam_a_coordenada_que_define_cada_extremo(cat):
    # a ficha técnica do plano traz, para norte e sul, a latitude extrema; para leste e oeste, a longitude
    r = gt.coordenadas_extremas(cat, "limite_uc")
    assert r["norte"]["coordenada_extrema"] == gt.graus_para_gms(r["norte"]["lat"]) + " S"
    assert r["sul"]["coordenada_extrema"] == gt.graus_para_gms(r["sul"]["lat"]) + " S"
    assert r["leste"]["coordenada_extrema"] == gt.graus_para_gms(r["leste"]["lon"]) + " O"
    assert r["oeste"]["coordenada_extrema"] == gt.graus_para_gms(r["oeste"]["lon"]) + " O"


def test_municipios_intersectados_divide_a_uc_meio_a_meio(cat):
    r = gt.municipios_intersectados(cat, "limite_uc")
    por_nome = {m["municipio"]: m for m in r["municipios"]}
    assert por_nome["Alfa"]["area_ha"] == 100.00 and por_nome["Alfa"]["percentual"] == 50.00
    assert por_nome["Beta"]["area_ha"] == 100.00 and por_nome["Beta"]["percentual"] == 50.00
    assert r["area_total_ha"] == 200.00
    assert r["area_fora_da_malha_ha"] == 0.00


# --------------------------------------------------------------------------
# 5.1 a 5.5 Zoneamento
# --------------------------------------------------------------------------


def test_calcular_area_zonas_monta_a_tabela_de_areas(cat):
    r = gt.calcular_area_zonas(cat)
    areas = {z["sigla"]: z["area_ha"] for z in r["zonas"]}
    assert areas == {"ZC": 150.00, "ZAA": 40.00, "ZI": 5.00, "ZDIP": 5.00}
    assert r["total_ha"] == 200.00


def test_calcular_area_zonas_confere_a_soma_com_o_limite_da_uc(cat):
    r = gt.calcular_area_zonas(cat)
    assert r["area_limite_uc_ha"] == 200.00
    assert r["diferenca_para_o_limite_ha"] == 0.00
    assert r["sobreposicao_entre_zonas_ha"] == 0.00


def test_calcular_area_zonas_traz_a_zona_de_amortecimento_fora_do_total(cat):
    r = gt.calcular_area_zonas(cat)
    # anel de 500 m: 2 (2000 + 1000) 500 + pi 500² = 3.785.398 m²
    assert r["zona_amortecimento_ha"] == pytest.approx(378.54, abs=0.02)


def test_percentual_por_zona_soma_cem(cat):
    r = gt.percentual_por_zona(cat)
    pct = {z["sigla"]: z["percentual"] for z in r["zonas"]}
    assert pct == {"ZC": 75.00, "ZAA": 20.00, "ZI": 2.50, "ZDIP": 2.50}
    assert r["soma_percentual"] == 100.00


def test_zona_da_coordenada_identifica_a_zona_do_ponto(cat):
    lon, lat = lonlat(E0 + 1700, N0 + 500)
    r = gt.zona_da_coordenada(cat, lon, lat)
    assert r["dentro_da_uc"] is True
    assert r["sigla"] == "ZAA"
    assert r["zona"] == "Zona de Adequação Ambiental"
    assert r["utm_e"] == pytest.approx(E0 + 1700, abs=0.01)


def test_zona_da_coordenada_fora_da_uc_e_dentro_da_zona_de_amortecimento(cat):
    lon, lat = lonlat(E0 + 2200, N0 + 500)
    r = gt.zona_da_coordenada(cat, lon, lat)
    assert r["dentro_da_uc"] is False
    assert r["sigla"] is None
    assert r["dentro_da_zona_de_amortecimento"] is True
    assert r["distancia_ao_limite_da_uc_m"] == pytest.approx(200.0, abs=0.01)


def test_zona_da_coordenada_longe_da_uc_avisa_possivel_troca_de_lon_e_lat(cat):
    lon, lat = lonlat(E0 + 1700, N0 + 500)
    r = gt.zona_da_coordenada(cat, lat, lon)  # trocados de propósito
    assert r["dentro_da_uc"] is False
    assert "lon" in r["aviso"] and "lat" in r["aviso"]


def test_zona_da_coordenada_recusa_latitude_impossivel(cat):
    with pytest.raises(gt.ErroGeo):
        gt.zona_da_coordenada(cat, -51.9, -125.0)


# --------------------------------------------------------------------------
# 5.4 a 5.6 Distância, interseção e buffer
# --------------------------------------------------------------------------


def test_distancia_ate_mede_cada_feicao_de_destino(cat):
    r = gt.distancia_ate(cat, "limite_uc", "estruturas")
    d = {f["feicao"]: f["distancia_m"] for f in r["feicoes"]}
    assert d == {"Posto": 0.00, "Mirante": 250.00}
    assert r["distancia_minima_m"] == 0.00


def test_distancia_ate_a_partir_de_uma_zona(cat):
    # a ZC termina em E0+1500; o mirante está em E0+2250
    r = gt.distancia_ate(cat, "zoneamento", "estruturas", feicao_origem="ZC", feicao_destino="Mirante")
    assert r["distancia_minima_m"] == 750.00


def test_intersecao_entre_poligonos_da_area_e_percentuais(cat):
    r = gt.intersecao(cat, "limite_uc", "municipios", feicao_b="Alfa")
    assert r["area_intersecao_ha"] == 100.00
    assert r["percentual_de_a"] == 50.00


def test_intersecao_de_linha_com_poligono_da_comprimento(cat):
    r = gt.intersecao(cat, "rodovias", "limite_uc")
    assert r["comprimento_intersecao_km"] == 2.00
    assert "area_intersecao_ha" not in r


def test_intersecao_vazia_devolve_zero(cat):
    r = gt.intersecao(cat, "zoneamento", "municipios", feicao_a="ZC", feicao_b="Beta")
    # a ZC vai até E0+1500 e Beta começa em E0+1000: 500 m x 1000 m = 50 ha
    assert r["area_intersecao_ha"] == 50.00
    r = gt.intersecao(cat, "zoneamento", "municipios", feicao_a="ZI", feicao_b="Alfa")
    assert r["area_intersecao_ha"] == 0.00


def test_calcular_buffer_de_500_m_em_volta_do_retangulo(cat):
    r = gt.calcular_buffer(cat, "limite_uc", 500)
    # retângulo + 4 faixas + 4 quartos de círculo = 200 + 300 + 78,54 ha
    assert r["area_original_ha"] == 200.00
    assert r["area_buffer_ha"] == pytest.approx(578.54, abs=0.01)
    assert r["area_faixa_ha"] == pytest.approx(378.54, abs=0.01)


def test_calcular_buffer_recusa_distancia_nao_positiva(cat):
    with pytest.raises(gt.ErroGeo):
        gt.calcular_buffer(cat, "limite_uc", 0)


def test_buffer_de_coordenada_tem_raio_geodesico_exato():
    # todos os vértices do buffer têm de estar a 500 m do centro medidos sobre o elipsoide
    lon, lat = -46.6333, -23.5505
    poligono = gt.buffer_geodesico(lon, lat, 500.0)
    geod = Geod(ellps="GRS80")
    for x, y in poligono.exterior.coords:
        assert geod.inv(lon, lat, x, y)[2] == pytest.approx(500.0, abs=0.01)


def test_calcular_buffer_coordenada_da_a_area_do_circulo(cat):
    r = gt.calcular_buffer_coordenada(-46.6333, -23.5505, 500.0)
    assert r["status"] == "sucesso"
    assert r["raio_aplicado_m"] == 500.0
    assert r["area_total_ha"] == round(math.pi * 500**2 / 1e4, 2) == 78.54


# --------------------------------------------------------------------------
# 5.3 e 5.6 Uso do solo
# --------------------------------------------------------------------------


def test_uso_solo_na_area_reparte_a_uc_entre_floresta_e_lavoura(cat):
    r = gt.uso_solo_na_area(cat, "limite_uc")
    classes = {c["classe"]: c for c in r["classes"]}
    assert classes["Cobertura arbórea"]["area_ha"] == 100.00
    assert classes["Lavoura"]["area_ha"] == 100.00
    assert classes["Lavoura"]["percentual"] == 50.00
    assert r["area_total_ha"] == 200.00


def test_uso_solo_na_area_de_uma_zona(cat):
    r = gt.uso_solo_na_area(cat, "zoneamento", "ZAA")
    assert [(c["classe"], c["area_ha"]) for c in r["classes"]] == [("Lavoura", 40.00)]


# --------------------------------------------------------------------------
# 6.1 Mapa
# --------------------------------------------------------------------------


def test_gerar_mapa_grava_um_png_com_o_zoneamento(cat, tmp_path):
    r = gt.gerar_mapa(cat, tema="zoneamento", pasta_saida=tmp_path)
    arquivo = tmp_path / r["arquivo_png"]
    assert arquivo.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert arquivo.stat().st_size > 20_000
    assert r["zonas_desenhadas"] == ["ZC", "ZAA", "ZI", "ZDIP"]


def test_gerar_mapa_recusa_tema_desconhecido(cat, tmp_path):
    with pytest.raises(gt.ErroGeo):
        gt.gerar_mapa(cat, tema="geologia", pasta_saida=tmp_path)


# --------------------------------------------------------------------------
# Procedência vinda do próprio dado (o shapefile oficial substitui o provisório)
# --------------------------------------------------------------------------


def test_colunas_fonte_e_provisorio_do_dado_valem_mais_que_o_catalogo(tmp_path):
    import geopandas as gpd
    import yaml
    from shapely.geometry import box

    gpd.GeoDataFrame({"sigla": ["ZC"], "zona": ["Zona de Conservação"], "fonte": ["Shapefile oficial"], "provisorio": [False]},
                     geometry=[box(0, 0, 10, 10)], crs=31982).to_file(tmp_path / "b.gpkg", layer="zoneamento")
    (tmp_path / "c.yaml").write_text(yaml.safe_dump({"crs_trabalho": 31982, "camadas": {"zoneamento": {
        "arquivo": "b.gpkg", "camada": "zoneamento", "campo_sigla": "sigla", "fonte": "figuras", "provisorio": True}}}))
    cat = gt.Catalogo(tmp_path / "c.yaml")
    assert cat.procedencia("zoneamento") == {"fontes": {"zoneamento": "Shapefile oficial"}, "provisorio": False}
    assert gt.carregar_camada(cat, "zoneamento")["provisorio"] is False
