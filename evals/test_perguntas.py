"""As perguntas da avaliação saem dos dados carregados, não de uma UC fixa."""
from __future__ import annotations

from rodar_agente import gerar_perguntas, valores_esperados

from agente import carregar_skill


def test_perguntas_cobrem_so_o_que_existe_e_todas_tem_resposta_calculavel(cat):
    perguntas = gerar_perguntas(cat)
    ids = [p["id"] for p in perguntas]
    assert len(ids) == len(set(ids))
    texto = " ".join(p["pergunta"] for p in perguntas)
    for zona in ("Zona de Conservação", "Zona de Adequação Ambiental", "Zona de Infraestrutura", "Zona de Diferentes Interesses Públicos"):
        assert zona in texto
    assert "Zona de Preservação" in texto  # inexistente na UC sintética: pergunta de robustez
    assert any("rodovias" in p["pergunta"] for p in perguntas)  # camada de linhas fornecida
    assert {"rvf_condicao", "rvf_entorno", "rvf_sem_recursos"} <= set(ids)  # tópico 4.1
    for p in perguntas:
        skill = carregar_skill(p["skill"])
        assert set(p["tools"]) <= set(skill["tools"]), p["id"]  # a skill autoriza a tool cobrada
        valores_esperados(cat, p)  # o gabarito de cada pergunta é calculável


def test_ponto_da_pergunta_cai_na_zona_esperada(cat):
    import geotools as gt
    p = next(p for p in gerar_perguntas(cat) if p["id"] == "ponto_zona")
    lon, lat = p["ponto"]
    assert gt.zona_da_coordenada(cat, lon, lat)["sigla"] == p["sigla_esperada"]


def test_zona_do_ponto_e_zona_inexistente_sao_julgadas_pela_resposta(cat):
    from rodar_agente import julgar
    perguntas = {p["id"]: p for p in gerar_perguntas(cat)}
    ponto, ausente = perguntas["ponto_zona"], perguntas["zona_inexistente"]
    rastro = lambda resposta: {"pergunta": "", "resposta": resposta, "chamadas": []}  # noqa: E731
    assert julgar(ponto, rastro(f"O ponto cai na {ponto['sigla_esperada']}."), [], True)["acertou_valores"] is True
    assert julgar(ponto, rastro("O ponto cai na ZXX."), [], True)["acertou_valores"] is False
    assert julgar(ausente, rastro("Essa zona não existe nesta UC."), [], True)["acertou_valores"] is True
    assert julgar(ausente, rastro("Ela tem 30,5 ha."), [], True)["acertou_valores"] is False


def test_caminho_com_ponto_no_nome_da_classe():
    from rodar_agente import valor_no_caminho
    r = {"classes": [{"classe": "Form. Florestal", "area_ha": 12.5}]}
    assert valor_no_caminho(r, "classes.Form. Florestal.area_ha") == 12.5
    assert valor_no_caminho({"area_ha": 3}, "area_ha") == 3
