"""Comparação dos números calculados com os publicados no plano (gabarito do usuário)."""
from __future__ import annotations

from comparacao import comparar


def test_compara_so_o_que_o_gabarito_traz_com_tolerancia_das_casas_publicadas(cat):
    linhas = {l["grandeza"]: l for l in comparar(cat, {
        "area_uc_ha": 200.0,              # 1 casa publicada: tolerância 0,05
        "zonas_ha": {"ZAA": 40.004, "ZP": 10},  # ZP não existe nos dados
        "municipios_percentual": {"Alfa": 51},  # inteiro: tolerância 0,5; dado é 50,00
    })}
    assert linhas["Área da UC"]["dentro_da_tolerancia"] and linhas["Área da UC"]["tolerancia"] == 0.05
    assert linhas["Área da ZAA"]["tolerancia"] == 0.0005 and linhas["Área da ZAA"]["dentro_da_tolerancia"] is False
    assert linhas["Área da ZP"]["plataforma"] is None and linhas["Área da ZP"]["dentro_da_tolerancia"] is False
    assert linhas["Parcela da UC em Alfa"]["dentro_da_tolerancia"] is False
    assert "Perímetro da UC" not in linhas  # não veio no gabarito, não é comparado


def test_extremos_em_segundos_de_arco(cat):
    from geotools import coordenadas_extremas
    norte = coordenadas_extremas(cat, "limite_uc")["norte"]["coordenada_extrema"].removesuffix(" S")
    l = comparar(cat, {"extremos": {"norte_lat": norte}})[0]
    assert l["dentro_da_tolerancia"] and l["unidade"] == "segundos de arco"
