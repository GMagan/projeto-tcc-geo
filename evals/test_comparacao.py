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


def test_zero_final_do_plano_conta_como_casa_publicada(cat):
    from comparacao import ler_gabarito
    linha = comparar(cat, ler_gabarito("area_uc_ha: 200.00\n"))[0]  # YAML leria 200.0
    assert linha["tolerancia"] == 0.005 and linha["dentro_da_tolerancia"]


def test_extremos_em_segundos_de_arco(cat):
    from geotools import coordenadas_extremas
    norte = coordenadas_extremas(cat, "limite_uc")["norte"]["coordenada_extrema"].removesuffix(" S")
    l = comparar(cat, {"extremos": {"norte_lat": norte}})[0]
    assert l["dentro_da_tolerancia"] and l["unidade"] == "segundos de arco"


def test_extremo_em_graus_decimais(cat):
    from comparacao import ler_gabarito
    from geotools import coordenadas_extremas
    lat = round(coordenadas_extremas(cat, "limite_uc")["norte"]["lat"], 4)
    l = comparar(cat, ler_gabarito(f"extremos: {{norte_lat: {lat}}}\n"))[0]
    assert l["dentro_da_tolerancia"] and l["tolerancia"] == 0.18  # meia unidade de 0,0001° em segundos


def test_gabarito_mal_escrito_vira_mensagem_clara(cat):
    import pytest
    from comparacao import ErroGabarito, ler_gabarito
    with pytest.raises(ErroGabarito, match="norte_lat"):
        comparar(cat, ler_gabarito('extremos: {norte: "25° 37\' 46,846\\""}\n'))
    with pytest.raises(ErroGabarito, match="graus decimais"):
        comparar(cat, ler_gabarito('extremos: {norte_lat: "25° 37"}\n'))


def test_numero_com_virgula_vira_erro_de_gabarito_e_nao_derruba_o_make(cat):
    import pytest
    from comparacao import ErroGabarito, ler_gabarito
    for texto in ("area_uc_ha: 616,86\n", "zonas_ha: {ZC: }\n"):
        with pytest.raises(ErroGabarito, match="não é número"):
            comparar(cat, ler_gabarito(texto))


def test_nome_de_municipio_e_sigla_sem_diferenciar_caixa_e_acento(cat):
    linhas = {l["grandeza"]: l for l in comparar(cat, {"municipios_percentual": {"ALFA": 50}, "zonas_ha": {"zc": 150}})}
    assert linhas["Parcela da UC em ALFA"]["plataforma"] == 50.0
    assert linhas["Área da zc"]["plataforma"] == 150.0
