"""Testes do juiz determinístico de fidelidade numérica.

O juiz responde, sem modelo de linguagem, à pergunta central do trabalho:
todo número da resposta do agente veio de uma tool?
"""
from __future__ import annotations

from juiz_numerico import avaliar, extrair_numeros

RESULTADO_TOOL = {"status": "sucesso", "area_ha": 616.66, "perimetro_km": 13.85, "crs_calculo": "EPSG:31982", "provisorio": True}
RASTRO = {
    "pergunta": "Qual a área do parque?",
    "chamadas": [{"tool": "calcular_area", "argumentos": {"camada": "limite_uc"}, "resultado": RESULTADO_TOOL}],
}


def test_extrai_numeros_nos_formatos_brasileiro_e_internacional():
    texto = "A ZA tem 1.622,48 ha; a UC, 616.66 ha (87,28%), em lon -51.9750."
    assert extrair_numeros(texto) == [1622.48, 616.66, 87.28, -51.975]


def test_extrai_graus_minutos_e_segundos_como_tres_numeros():
    assert extrair_numeros("Norte: 25° 37' 46,846\"") == [25.0, 37.0, 46.846]


def test_numero_copiado_da_tool_e_fiel():
    r = avaliar("A área é de 616,66 ha e o perímetro, 13,85 km (EPSG:31982).", RASTRO)
    assert r["fidelidade"] == 1.0
    assert r["numeros_sem_origem"] == []
    assert r["alucinacao_numerica"] is False


def test_numero_que_nao_veio_de_tool_e_alucinacao():
    r = avaliar("A área é de 616,66 ha, cerca de 0,5% do município.", RASTRO)
    assert r["numeros_sem_origem"] == [0.5]
    assert r["alucinacao_numerica"] is True
    assert r["fidelidade"] == 0.5


def test_arredondamento_feito_pelo_modelo_conta_como_infiel_mas_fica_registrado():
    r = avaliar("A área é de aproximadamente 616,7 ha.", RASTRO)
    assert r["numeros_sem_origem"] == [616.7]
    assert r["numeros_arredondados"] == [616.7]


def test_inteiros_pequenos_de_enumeracao_nao_sao_cobrados():
    r = avaliar("São 2 medidas: 1) área de 616,66 ha; 2) perímetro de 13,85 km.", RASTRO)
    assert r["numeros_sem_origem"] == []
    assert r["n_numeros"] == 2  # só as medidas contam


def test_numero_que_esta_na_pergunta_pode_ser_repetido():
    rastro = {"pergunta": "Qual a área de uma faixa de 3000 m em volta do parque?", "chamadas": [{"tool": "calcular_buffer", "argumentos": {"distancia_m": 3000}, "resultado": {"area_faixa_ha": 4711.02}}]}
    r = avaliar("A faixa de 3000 m tem 4.711,02 ha.", rastro)
    assert r["numeros_sem_origem"] == []


def test_resposta_sem_tool_nao_tem_origem_para_nenhum_numero():
    r = avaliar("A área é de cerca de 620 ha.", {"pergunta": "Qual a área do parque?", "chamadas": []})
    assert r["numeros_sem_origem"] == [620.0]
    assert r["chamou_tool"] is False


def test_confere_tool_esperada_valor_esperado_crs_e_aviso_de_provisorio():
    r = avaliar(
        "A área é de 616,66 ha (SIRGAS 2000 / UTM 22S). O dado é provisório.",
        RASTRO, tools_esperadas=["calcular_area"], valores_esperados=[616.66],
    )
    assert r["usou_tool_esperada"] is True
    assert r["acertou_valores"] is True
    assert r["citou_crs"] is True
    assert r["avisou_provisorio"] is True

    r = avaliar("A área é de 616,66 ha.", RASTRO, tools_esperadas=["calcular_area_zonas"], valores_esperados=[538.37])
    assert r["usou_tool_esperada"] is False
    assert r["acertou_valores"] is False
    assert r["citou_crs"] is False
    assert r["avisou_provisorio"] is False


def test_inteiro_pequeno_com_unidade_e_medida_e_e_cobrado():
    # pergunta sobre zona que não existe: "8 ha" inventado não pode passar por enumeração
    r = avaliar("A Zona de Uso Intensivo tem 8 ha e fica a 5 km da sede (10%).", {"pergunta": "Qual a área da ZUI?", "chamadas": []})
    assert r["numeros_sem_origem"] == [8.0, 5.0, 10.0]
    assert r["alucinacao_numerica"] is True


def test_sem_numero_esperado_nao_conta_como_valor_certo():
    assert avaliar("Não sei.", {"chamadas": []}, valores_esperados=[])["acertou_valores"] is None
