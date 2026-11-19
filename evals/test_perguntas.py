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
    for p in perguntas:
        skill = carregar_skill(p["skill"])
        assert set(p["tools"]) <= set(skill["tools"]), p["id"]  # a skill autoriza a tool cobrada
        valores_esperados(cat, p)  # o gabarito de cada pergunta é calculável


def test_ponto_da_pergunta_cai_na_zona_esperada(cat):
    import geotools as gt
    p = next(p for p in gerar_perguntas(cat) if p["id"] == "ponto_zona")
    lon, lat = p["ponto"]
    assert gt.zona_da_coordenada(cat, lon, lat)["sigla"] == p["sigla_esperada"]
