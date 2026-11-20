#!/usr/bin/env python3
"""Calcula com as tools tudo o que vale relatar sobre a UC carregada e grava em resultados/.

  resultados/resumo.json                 todos os valores (e a resposta completa de cada tool)
  resultados/tabelas/dados/tabelas.json  tabelas já formatadas (padrão brasileiro)
  resultados/tabelas/dados/numeros.json  números soltos (área da UC, de cada zona etc.)
  resultados/mapas/                      mapas de zoneamento e de zona de amortecimento
  resultados/pytest.xml                  resultado dos testes

Só entra o que os dados permitem: sem camada de municípios não há tabela de municípios, etc.

Uso:  python scripts/gerar_resultados.py      (o `make` já chama)
"""
from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "mcp-python"), str(RAIZ / "evals")]

import geotools as gt  # noqa: E402
from geotools import br  # noqa: E402
from comparacao import ErroGabarito, carregar_gabarito, comparar  # noqa: E402

SAIDA = RAIZ / "resultados"
DADOS = SAIDA / "tabelas" / "dados"


def rodar_testes() -> dict:
    xml = SAIDA / "pytest.xml"
    xml.unlink(missing_ok=True)  # xml velho de outra rodada não pode passar por resultado desta
    rodada = subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={xml}", "-p", "no:cacheprovider"],
                            cwd=RAIZ, capture_output=True, text=True, check=False)
    if not xml.exists():
        print(f"aviso: os testes não rodaram:\n{(rodada.stdout + rodada.stderr)[-2000:]}")
        return {"nao_rodou": 1}
    contagem = Counter()
    for caso in ET.parse(xml).getroot().iter("testcase"):
        if caso.find("failure") is not None or caso.find("error") is not None:
            contagem["falhou"] += 1
        elif caso.find("skipped") is not None:
            contagem["pulado"] += 1
        else:
            contagem["passou"] += 1
    return dict(contagem)


def projecao(cat: gt.Catalogo) -> dict:
    """Área da UC no sistema de trabalho, no elipsoide e em Web Mercator (o erro de quem usa EPSG:3857)."""
    geom = cat.ler("limite_uc")
    utm = float(geom.geometry.union_all().area) / 1e4
    mercator = float(geom.to_crs(3857).geometry.union_all().area) / 1e4
    geodesica = gt.calcular_area(cat, "limite_uc")["area_geodesica_ha"]
    return {"utm_ha": utm, "geodesica_ha": geodesica, "mercator_ha": mercator,
            "erro_utm_pct": 100 * (utm - geodesica) / geodesica, "erro_mercator_pct": 100 * (mercator - geodesica) / geodesica}


def uso_solo_por_area(cat: gt.Catalogo, alvos: dict[str, tuple[str, str]]) -> dict:
    """Uso do solo de cada área; a que o raster não cobre (raster recortado na UC e a ZA, por exemplo) fica de fora com aviso."""
    saida = {}
    for nome, (camada, feicao) in alvos.items():
        try:
            saida[nome] = gt.uso_solo_na_area(cat, camada, feicao)
            if aviso := saida[nome].get("aviso_cobertura"):
                print(f"aviso: {nome}: {aviso}")
        except gt.ErroGeo as erro:
            print(f"aviso: {nome} sem uso do solo: {erro}")
    return saida


def main() -> None:
    caminho = RAIZ / "dados" / "catalogo.yaml"
    if not caminho.exists():
        sys.exit("sem dados importados: coloque os arquivos em dados/entrada/ e rode `make`")
    DADOS.mkdir(parents=True, exist_ok=True)
    cat = gt.Catalogo(caminho)
    tem = cat.camadas.__contains__
    r: dict = {"uc": cat.uc, "epsg": cat.epsg}
    tabelas: dict[str, dict] = {}

    def tabela(nome, cabecalho, linhas):
        tabelas[nome] = {"cabecalho": cabecalho, "linhas": linhas}

    r["camadas"] = [gt.carregar_camada(cat, c) for c in cat.camadas]
    tabela("camadas", ["Camada", "Fonte", "Feições"], [[c["camada"], c["fonte"], str(c["n_feicoes"])] for c in r["camadas"]])

    r["area_uc"] = gt.calcular_area(cat, "limite_uc")
    r["extremos"] = gt.coordenadas_extremas(cat, "limite_uc")
    ficha = [["Superfície", f"{br(r['area_uc']['area_ha'])} ha"], ["Perímetro", f"{br(r['area_uc']['perimetro_km'])} km"]]
    ficha += [[f"Extremo {k}", r["extremos"][k]["gms"]] for k in ("norte", "sul", "leste", "oeste")]
    if tem("municipios"):
        r["municipios"] = gt.municipios_intersectados(cat)
        ficha += [[f"Município: {m['municipio']}", f"{br(m['area_ha'])} ha ({br(m['percentual'])} %)"] for m in r["municipios"]["municipios"]]
    tabela("ficha_tecnica", ["Campo", "Valor"], ficha)

    r["zonas"] = gt.percentual_por_zona(cat)
    r["area_zonas"] = gt.calcular_area_zonas(cat)
    linhas = [[f"{z['zona']} ({z['sigla']})", br(z["area_ha"]), br(z["percentual"])] for z in r["zonas"]["zonas"]]
    linhas.append(["Total", br(r["zonas"]["total_ha"]), "100,00"])
    if "zona_amortecimento_ha" in r["area_zonas"]:
        linhas.append(["Zona de Amortecimento (ZA)", br(r["area_zonas"]["zona_amortecimento_ha"]), "---"])
        r["faixas"] = [gt.calcular_buffer(cat, "limite_uc", d) for d in (1000, 2000, 3000)]
        za = r["area_zonas"]["zona_amortecimento_ha"]
        tabela("faixas", ["Entorno", "Área (ha)", "ZA / faixa"],
               [[f"Faixa de {int(f['distancia_m'] / 1000)} km", br(f["area_faixa_ha"]), f"{br(100 * za / f['area_faixa_ha'], 1)} %"] for f in r["faixas"]])
    tabela("zonas", ["Zona", "Área (ha)", "%"], linhas)

    if "uso_solo" in cat.rasters:
        alvos = {"UC": ("limite_uc", "")} | {z["sigla"]: ("zoneamento", z["sigla"]) for z in r["zonas"]["zonas"]}
        if tem("zona_amortecimento"):
            alvos["ZA"] = ("zona_amortecimento", "")
        r["uso_solo"] = uso_solo_por_area(cat, alvos)
        tabela("uso_solo", ["Área", "Classe", "Área (ha)", "%"],
               [[nome, c["classe"], br(c["area_ha"]), br(c["percentual"], 1)] for nome, u in r["uso_solo"].items() for c in u["classes"]])

    r["projecao"] = projecao(cat)
    p = r["projecao"]
    tabela("projecao", ["Sistema", "Área da UC (ha)", "Erro"], [
        ["Elipsoide (referência)", br(p["geodesica_ha"]), "---"],
        [f"UTM (EPSG:{cat.epsg})", br(p["utm_ha"]), f"{br(p['erro_utm_pct'], 3)} %"],
        ["Web Mercator (EPSG:3857)", br(p["mercator_ha"]), f"{br(p['erro_mercator_pct'], 2)} %"]])

    try:
        r["gabarito"] = comparar(cat, carregar_gabarito(cat))
    except ErroGabarito as erro:  # um erro no gabarito do usuário não bloqueia o resto dos resultados
        print(f"aviso: gabarito.yaml ignorado: {erro}")
        r["gabarito"] = []
    if r["gabarito"]:
        tabela("gabarito", ["Grandeza", "Plano", "Calculado", "Erro", "Tolerância", "Bate?"], [
            [f"{l['grandeza']} ({l['unidade']})", br(l["plano"], 3), br(l["plataforma"], 3), br(l["erro"], 3), br(l["tolerancia"], 4),
             "sim" if l["dentro_da_tolerancia"] else "NÃO"] for l in r["gabarito"]])

    r["mapas"] = [gt.gerar_mapa(cat, "zoneamento", SAIDA / "mapas")]
    if tem("zona_amortecimento"):
        r["mapas"].append(gt.gerar_mapa(cat, "zona_amortecimento", SAIDA / "mapas"))

    r["testes"] = rodar_testes()
    r["llm"] = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted((SAIDA / "llm").glob("*/resumo.json"))}
    if r["llm"]:
        pct = lambda v: "---" if v is None else f"{br(100 * v, 1)} %"  # noqa: E731
        tabela("avaliacao_ia", ["Modelo", "Condição", "N", "Tool certa", "Valor certo", "Com nº sem origem", "s/pergunta"], [
            [m["modelo"], cond, str(m["n_perguntas"]), pct(m["taxa_tool_esperada"]), pct(m["taxa_acerto_valores"]),
             pct(m["taxa_alucinacao_numerica"]), br(m["segundos_medio"], 1)] for cond_m in r["llm"].values() for cond, m in cond_m.items()])

    numeros = {"uc": cat.uc.get("nome"), "sigla": cat.uc.get("sigla"), "epsg": cat.epsg,
               "area_uc_ha": r["area_uc"]["area_ha"], "perimetro_km": r["area_uc"]["perimetro_km"],
               "zonas_ha": {z["sigla"]: z["area_ha"] for z in r["zonas"]["zonas"]},
               "zonas_pct": {z["sigla"]: z["percentual"] for z in r["zonas"]["zonas"]},
               "zona_amortecimento_ha": r["area_zonas"].get("zona_amortecimento_ha"),
               "erro_mercator_pct": round(p["erro_mercator_pct"], 2), "testes": r["testes"],
               "gabarito_bate": f"{sum(l['dentro_da_tolerancia'] for l in r['gabarito'])}/{len(r['gabarito'])}" if r["gabarito"] else None,
               "ia_avaliada": bool(r["llm"])}
    (DADOS / "numeros.json").write_text(json.dumps(numeros, indent=2, ensure_ascii=False), encoding="utf-8")
    (DADOS / "tabelas.json").write_text(json.dumps(tabelas, indent=2, ensure_ascii=False), encoding="utf-8")
    (SAIDA / "resumo.json").write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"{cat.uc.get('nome')}: {br(r['area_uc']['area_ha'])} ha, {len(r['zonas']['zonas'])} zonas, EPSG:{cat.epsg}")
    if r["gabarito"]:
        print(f"comparação com o plano: {numeros['gabarito_bate']} números batem")
        for l in r["gabarito"]:
            if not l["dentro_da_tolerancia"]:
                print(f"  não bate: {l['grandeza']}: plano {l['plano']} x calculado {l['plataforma']}")
    print(f"testes: {r['testes']}")
    print("resultados em resultados/ (resumo.json, tabelas/, mapas/)")


if __name__ == "__main__":
    main()
