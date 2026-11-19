"""Modo IA do importador: a IA diz o que é cada arquivo; o programa confere tudo.

O modelo é roteirizado (respostas fixas), para testar o que o programa faz com
uma resposta boa, com uma resposta que inventa coisas e com uma resposta inválida.
"""
from __future__ import annotations

import json

import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

import geotools as gt
from agente import ModeloRoteirizado, carregar_skill
from scripts.importar_com_ia import importar_com_ia, inventariar
from scripts.importar_dados import ErroImportacao

E0, N0, EPSG = 800_000, 9_650_000, 31980


@pytest.fixture
def pasta(tmp_path):
    """Dados com nomes que o modo por regras não entende."""
    entrada = tmp_path / "dados" / "entrada"
    entrada.mkdir(parents=True)
    gpd.GeoDataFrame({"TIPO": ["Núcleo intocável", "Visitação"]},
                     geometry=[box(E0, N0, E0 + 1000, N0 + 1000), box(E0 + 1000, N0, E0 + 2000, N0 + 1000)],
                     crs=EPSG).to_file(entrada / "areas_manejo.gpkg")
    gpd.GeoDataFrame({"NM_CIDADE": ["Alfa", "Beta"]},
                     geometry=[box(E0 - 9000, N0 - 9000, E0 + 1000, N0 + 9000), box(E0 + 1000, N0 - 9000, E0 + 9000, N0 + 9000)],
                     crs=EPSG).to_file(entrada / "cidades.gpkg")
    gpd.GeoDataFrame({"nome": ["Ramal 1"]}, geometry=[LineString([(E0 - 500, N0 + 500), (E0 + 2500, N0 + 500)])],
                     crs=EPSG).to_file(entrada / "vias.gpkg")
    (entrada / "leia.txt").write_text("Dados do Parque Natural Municipal do Vale (PNMV), 2026.", encoding="utf-8")
    return tmp_path / "dados"


def resposta(conteudo) -> ModeloRoteirizado:
    texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False)
    return ModeloRoteirizado([{"role": "assistant", "content": texto}])


BOA = {
    "uc": {"nome": "Parque Natural Municipal do Vale", "sigla": "PNMV"},
    "arquivos": [
        {"arquivo": "areas_manejo.gpkg", "papel": "zoneamento", "coluna_zona": "TIPO"},
        {"arquivo": "cidades.gpkg", "papel": "municipios", "coluna_nome": "NM_CIDADE"},
        {"arquivo": "vias.gpkg", "papel": "camada", "nome_camada": "estradas"},
        {"arquivo": "leia.txt", "papel": "ignorar"},
    ],
    "zonas": {"Núcleo intocável": "ZP", "Visitação": "ZUM"},
}


def test_inventario_mostra_colunas_valores_e_texto(pasta):
    inv = {a["arquivo"]: a for a in inventariar(pasta / "entrada")}
    assert inv["cidades.gpkg"]["colunas"]["NM_CIDADE"] == ["Alfa", "Beta"]
    assert "Parque Natural Municipal do Vale" in inv["leia.txt"]["texto"]


def test_ia_mapeia_nomes_fora_do_padrao_e_o_importador_usa(pasta):
    modelo = resposta(BOA)
    rel = importar_com_ia(pasta, modelo)

    assert rel["descartado"] == []
    cat = gt.Catalogo(pasta / "catalogo.yaml")
    assert cat.uc == {"nome": "Parque Natural Municipal do Vale", "sigla": "PNMV"}
    assert {z["sigla"] for z in gt.calcular_area_zonas(cat)["zonas"]} == {"ZP", "ZUM"}
    assert {m["municipio"] for m in gt.municipios_intersectados(cat)["municipios"]} == {"Alfa", "Beta"}
    assert "estradas" in cat.camadas
    assert (pasta / "entrada" / "mapeamento.yaml").exists()
    # a IA recebeu o inventário real, governada pela skill de importação
    assert "NM_CIDADE" in modelo.recebido[0]["mensagens"][-1]["content"]
    assert modelo.recebido[0]["mensagens"][0]["content"] == carregar_skill("_importacao")["texto"]


def test_skill_de_importacao_lista_exatamente_as_zonas_que_o_programa_aceita():
    from scripts.importar_dados import NOME
    texto = carregar_skill("_importacao")["texto"]
    for sigla, nome in NOME.items():
        assert f"{sigla} = {nome}" in texto


def test_mapeamento_salvo_e_reaproveitado_sem_chamar_a_ia(pasta):
    importar_com_ia(pasta, resposta(BOA))
    sem_resposta = ModeloRoteirizado([])
    importar_com_ia(pasta, sem_resposta)
    assert sem_resposta.recebido == []


def test_o_que_a_ia_inventa_e_descartado_e_o_que_falta_e_perguntado(pasta):
    inventada = {
        "uc": {"nome": "Parque Fantasma", "sigla": "PF"},          # não aparece em nenhum arquivo
        "arquivos": [
            {"arquivo": "zonas_oficiais.shp", "papel": "zoneamento", "coluna_zona": "ZONA"},  # arquivo não existe
            {"arquivo": "areas_manejo.gpkg", "papel": "zoneamento", "coluna_zona": "CLASSE"},  # coluna não existe
            {"arquivo": "cidades.gpkg", "papel": "municipios", "coluna_nome": "NM_CIDADE"},
        ],
        "zonas": {"Área inventada": "ZC", "Visitação": "XYZ"},       # valor não existe; sigla inválida
    }
    with pytest.raises(ErroImportacao, match="zoneamento"):
        importar_com_ia(pasta, resposta(inventada))  # sem terminal: não completa nada sozinho

    perguntas = []
    respostas = iter(["areas_manejo.gpkg", "TIPO", "Parque Verdadeiro", "PV", "ZP", "ZUM"])

    def perguntar(pergunta, opcoes=None):
        perguntas.append(pergunta)
        return next(respostas)

    rel = importar_com_ia(pasta, resposta(inventada), perguntar=perguntar)

    descartes = " ".join(rel["descartado"])
    for coisa in ("zonas_oficiais.shp", "CLASSE", "Área inventada", "XYZ", "Parque Fantasma"):
        assert coisa in descartes
    cat = gt.Catalogo(pasta / "catalogo.yaml")
    assert cat.uc["nome"] == "Parque Verdadeiro"
    assert {z["sigla"] for z in gt.calcular_area_zonas(cat)["zonas"]} == {"ZP", "ZUM"}
    assert "municipios" in cat.camadas  # o que a IA acertou foi mantido


def test_resposta_que_nao_e_json_vira_pergunta(pasta):
    respostas = iter(["areas_manejo.gpkg", "TIPO", "Parque X", "PX", "ZP", "ZUM"])
    rel = importar_com_ia(pasta, resposta("Claro! Aqui está o mapeamento..."), perguntar=lambda p, o=None: next(respostas))
    assert any("JSON" in d for d in rel["descartado"])
    assert gt.Catalogo(pasta / "catalogo.yaml").uc["nome"] == "Parque X"


def test_mapeamento_recusado_nao_deixa_uc_nem_zonas_gravadas(pasta):
    with pytest.raises(ErroImportacao, match="não confirmado"):
        importar_com_ia(pasta, resposta(BOA), confirmar=lambda mapeamento, descartado: False)
    assert not (pasta / "entrada" / "uc.yaml").exists()
    assert not (pasta / "entrada" / "zonas.yaml").exists()


def test_inventario_lista_cada_camada_de_um_geopackage(tmp_path):
    gpkg = tmp_path / "projeto.gpkg"
    for camada in ("zonas", "rios"):
        gpd.GeoDataFrame({"x": [camada]}, geometry=[box(E0, N0, E0 + 10, N0 + 10)], crs=EPSG).to_file(gpkg, layer=camada)
    assert {i["arquivo"] for i in inventariar(tmp_path)} == {"projeto.gpkg/zonas", "projeto.gpkg/rios"}
