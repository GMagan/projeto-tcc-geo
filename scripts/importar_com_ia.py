#!/usr/bin/env python3
"""Modo IA de importação: a IA descobre o que é cada arquivo de dados/entrada/.

Para quem não quer seguir as convenções de nome do modo normal (`make`): o
usuário manda os arquivos como tiver ("cidades.shp", coluna "TIPO_AREA"...) e a
IA propõe o papel de cada um. A IA só *classifica*; ela não lê geometria nem
calcula nada. O fluxo:

  1. inventário (sem IA): nome, tipo, colunas e amostras de valores de cada arquivo;
  2. a IA propõe o mapeamento (papel de cada arquivo, colunas, significado das zonas, nome da UC);
  3. trava contra alucinação (sem IA): tudo é conferido contra o inventário; o que
     não existir nos dados é descartado e mostrado ao usuário;
  4. o que faltar de obrigatório (zoneamento, nome da UC, zonas) é perguntado no terminal;
  5. o mapeamento é salvo em dados/entrada/mapeamento.yaml (o usuário pode editar) e o
     importador normal (scripts/importar_dados.py) faz o resto.

Se mapeamento.yaml já existir, ele é reaproveitado (e conferido de novo) sem chamar a IA.
Para pedir um mapeamento novo à IA, apague o arquivo.

Uso:  python scripts/importar_com_ia.py      (o `make ia` já chama)
Modelo: LLM_BASE_URL e LLM_MODELO (padrão: Ollama local, qwen2.5:7b).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import geopandas as gpd
import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ)]

from agente import carregar_skill  # noqa: E402
from scripts.importar_dados import (  # noqa: E402
    NOME, RASTERS, VETORES, ErroImportacao, Perguntar, _ler_vetor, como_texto, listar_vetores, _normalizar, _perguntar_no_terminal, importar,
)

TEXTOS = (".txt", ".md", ".csv", ".yaml", ".yml", ".json")
ARQUIVOS_DO_PROGRAMA = ("mapeamento.yaml",)
PAPEIS_VETOR = ("zoneamento", "zona_amortecimento", "limite", "municipios", "camada", "ignorar")
PAPEIS_RASTER = ("uso_solo", "ignorar")
AMOSTRAS = 8

# As instruções da IA são uma skill (controle no SADT), editável sem mexer no código.
SKILL = "_importacao"


def inventariar(entrada: Path) -> list[dict]:
    """O que existe em entrada/, para a IA ler e para conferir o que ela disser."""
    itens = []
    for chave, p, camada in listar_vetores(entrada):
        try:
            gdf = _ler_vetor(p, camada)
        except ErroImportacao as erro:
            itens.append({"arquivo": chave, "tipo": "vetor", "erro": str(erro)})
            continue
        colunas = {c: [como_texto(v)[:60] for v in gdf[c].dropna().unique()[:AMOSTRAS]] for c in gdf.columns if c != "geometry"}
        itens.append({"arquivo": chave, "tipo": "vetor", "geometria": sorted(gdf.geom_type.unique()),
                      "n_feicoes": len(gdf), "colunas": colunas})
    for p in sorted(entrada.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or p.name in ARQUIVOS_DO_PROGRAMA:
            continue
        rel, sufixo = p.relative_to(entrada).as_posix(), p.suffix.lower()
        if sufixo in VETORES:
            continue
        elif sufixo in RASTERS:
            itens.append({"arquivo": rel, "tipo": "raster"})
        elif sufixo in TEXTOS:
            itens.append({"arquivo": rel, "tipo": "texto", "texto": p.read_text(encoding="utf-8", errors="replace")[:1500]})
        elif sufixo not in (".shx", ".dbf", ".prj", ".cpg", ".qmd", ".sbn", ".sbx", ".xml", ".aux"):
            itens.append({"arquivo": rel, "tipo": "outro"})
    return itens


def propor(inventario: list[dict], modelo) -> tuple[dict, list[str]]:
    """Pede o mapeamento à IA; devolve (proposta, problemas). Resposta inválida vira proposta vazia."""
    mensagens = [{"role": "system", "content": carregar_skill(SKILL)["texto"]},
                 {"role": "user", "content": "Inventário:\n" + json.dumps(inventario, ensure_ascii=False, indent=1)}]
    texto = modelo.conversar(mensagens, None).get("content") or ""
    inicio, fim = texto.find("{"), texto.rfind("}")
    try:
        proposta = json.loads(texto[inicio:fim + 1]) if inicio >= 0 else None
    except json.JSONDecodeError:
        proposta = None
    if not isinstance(proposta, dict):
        return {}, [f"a IA não devolveu um JSON válido (início da resposta: {texto[:80]!r})"]
    return proposta, []


def _texto_das_evidencias(inventario: list[dict]) -> str:
    partes = []
    for item in inventario:
        partes.append(item["arquivo"])
        partes += [f"{c} {' '.join(v)}" for c, v in item.get("colunas", {}).items()]
        partes.append(item.get("texto", ""))
    return _normalizar(" ".join(partes))


def validar(proposta: dict, inventario: list[dict]) -> tuple[dict, list[str]]:
    """Mantém só o que existe nos dados. Devolve (mapeamento conferido, descartes com o motivo)."""
    por_arquivo = {i["arquivo"]: i for i in inventario}
    descartado, arquivos = [], {}
    for item in proposta.get("arquivos") or []:
        if not isinstance(item, dict):
            continue
        nome, papel = str(item.get("arquivo")), item.get("papel")
        info = por_arquivo.get(nome)
        if info is None:
            descartado.append(f"arquivo '{nome}' não existe em dados/entrada/")
            continue
        validos = PAPEIS_VETOR if info["tipo"] == "vetor" else PAPEIS_RASTER if info["tipo"] == "raster" else ("ignorar",)
        if papel not in validos:
            descartado.append(f"{nome}: papel '{papel}' não serve para arquivo do tipo {info['tipo']}")
            continue
        conferido = {"papel": papel}
        colunas = info.get("colunas", {})
        if papel == "zoneamento":
            if item.get("coluna_zona") not in colunas:
                descartado.append(f"{nome}: coluna de zonas '{item.get('coluna_zona')}' não existe (colunas: {list(colunas)})")
                continue
            conferido["coluna_zona"] = item["coluna_zona"]
        if papel == "municipios" and item.get("coluna_nome"):
            if item["coluna_nome"] in colunas:
                conferido["coluna_nome"] = item["coluna_nome"]
            else:
                descartado.append(f"{nome}: coluna de nomes '{item['coluna_nome']}' não existe; o programa procura sozinho")
        if papel == "camada" and item.get("nome_camada"):
            conferido["nome_camada"] = str(item["nome_camada"])
        if papel == "uso_solo" and item.get("legenda"):
            if item["legenda"] in por_arquivo:
                conferido["legenda"] = item["legenda"]
            else:
                descartado.append(f"{nome}: legenda '{item['legenda']}' não existe")
        arquivos[nome] = conferido

    evidencias = _texto_das_evidencias(inventario)
    uc = {}
    nome_uc, sigla_uc = (proposta.get("uc") or {}).get("nome"), (proposta.get("uc") or {}).get("sigla")
    if nome_uc:
        if _normalizar(nome_uc) in evidencias:
            uc["nome"] = str(nome_uc)
            if sigla_uc and re.search(rf"\b{re.escape(_normalizar(sigla_uc))}\b", evidencias):
                uc["sigla"] = str(sigla_uc)
        else:
            descartado.append(f"nome da UC '{nome_uc}' não aparece em nenhum arquivo")
    return {"uc": uc, "arquivos": arquivos, "zonas": {}}, descartado


def validar_zonas(propostas: dict, arquivos: dict, entrada: Path) -> tuple[dict, list[str]]:
    """Mantém só valor de zona que existe na coluna de zonas e sigla do roteiro."""
    reais = set()  # todos os valores, não só as amostras do inventário
    onde = {chave: (p, camada) for chave, p, camada in listar_vetores(entrada)}
    for nome, m in arquivos.items():
        if m["papel"] == "zoneamento":
            reais |= {como_texto(v) for v in _ler_vetor(*onde[nome])[m["coluna_zona"]].dropna()}
    zonas, descartado = {}, []
    for valor, sigla in (propostas or {}).items():
        sigla = str(sigla).upper()
        if sigla not in NOME:
            descartado.append(f"zona '{valor}': sigla '{sigla}' não existe")
        elif str(valor) not in reais:
            descartado.append(f"zona '{valor}' não aparece na coluna de zonas")
        else:
            zonas[str(valor)] = sigla
    return zonas, descartado


def _escolher(perguntar: Perguntar, pergunta: str, opcoes: list[str]) -> str:
    while (resposta := perguntar(pergunta, opcoes).strip()) not in opcoes:
        print(f"  '{resposta}' não está na lista")
    return resposta


def importar_com_ia(pasta: Path, modelo, perguntar: Perguntar | None = None, confirmar=None) -> dict:
    """Mapeia com a IA (ou reaproveita mapeamento.yaml), confere, pergunta o que faltar e importa."""
    entrada = pasta / "entrada"
    inventario = inventariar(entrada)
    if not any(i["tipo"] == "vetor" for i in inventario):
        raise ErroImportacao(f"{entrada} não tem nenhum arquivo vetorial (.shp, .gpkg, .geojson, .zip)")
    salvo = entrada / "mapeamento.yaml"
    if salvo.exists():
        anterior = yaml.safe_load(salvo.read_text(encoding="utf-8")) or {}
        proposta = {**anterior, "arquivos": [{"arquivo": a, **m} for a, m in (anterior.get("arquivos") or {}).items()]}
        problemas, origem = [], "mapeamento.yaml"
    else:
        proposta, problemas = propor(inventario, modelo)
        origem = getattr(modelo, "nome", "IA")
    mapeamento, descartado = validar(proposta, inventario)
    descartado = problemas + descartado

    # obrigatório: zoneamento. O que a IA não achou é perguntado; nada é completado sozinho.
    if not any(m["papel"] == "zoneamento" for m in mapeamento["arquivos"].values()):
        vetores = [i for i in inventario if i["tipo"] == "vetor" and "colunas" in i]
        if perguntar is None:
            raise ErroImportacao("a IA não identificou o arquivo de zoneamento. Rode `make ia` num terminal para responder, "
                                 f"ou escreva {salvo} indicando o arquivo e a coluna das zonas")
        arquivo = _escolher(perguntar, "Qual arquivo tem o zoneamento?", [i["arquivo"] for i in vetores])
        colunas = list(next(i for i in vetores if i["arquivo"] == arquivo)["colunas"])
        coluna = _escolher(perguntar, f"Qual coluna de {arquivo} tem o nome das zonas?", colunas)
        mapeamento["arquivos"][arquivo] = {"papel": "zoneamento", "coluna_zona": coluna}
    mapeamento["zonas"], descartes_zonas = validar_zonas(proposta.get("zonas"), mapeamento["arquivos"], entrada)
    descartado += descartes_zonas

    salvo.write_text(f"# Mapeamento dos arquivos ({origem}), conferido contra os dados. Pode editar; apague para pedir um novo à IA.\n"
                     + yaml.safe_dump(mapeamento, allow_unicode=True, sort_keys=False), encoding="utf-8")
    if confirmar is not None and not confirmar(mapeamento, descartado):
        raise ErroImportacao(f"mapeamento não confirmado: edite {salvo} e rode `make ia` de novo")

    # só depois do "sim" do usuário. uc.yaml e zonas.yaml do usuário valem mais que a IA; o que faltar o importador pergunta
    if mapeamento["uc"].get("nome") and not (entrada / "uc.yaml").exists():
        uc = {"nome": mapeamento["uc"]["nome"], "sigla": mapeamento["uc"].get("sigla", "")}
        (entrada / "uc.yaml").write_text(yaml.safe_dump(uc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    if mapeamento["zonas"]:
        arquivo_zonas = entrada / "zonas.yaml"
        atuais = (yaml.safe_load(arquivo_zonas.read_text(encoding="utf-8")) or {}) if arquivo_zonas.exists() else {}
        arquivo_zonas.write_text(yaml.safe_dump({**mapeamento["zonas"], **atuais}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    rel = importar(pasta, perguntar, mapeamento)
    return {**rel, "descartado": descartado, "mapeamento": mapeamento}


def _confirmar_no_terminal(mapeamento: dict, descartado: list[str]) -> bool:
    print("\nMapeamento proposto (conferido contra os dados):")
    for arquivo, m in mapeamento["arquivos"].items():
        extras = ", ".join(f"{k}={v}" for k, v in m.items() if k != "papel")
        print(f"  {arquivo:35s} -> {m['papel']}{f' ({extras})' if extras else ''}")
    for valor, sigla in mapeamento["zonas"].items():
        print(f"  zona '{valor}' -> {sigla} ({NOME[sigla]})")
    if mapeamento["uc"]:
        print(f"  UC: {mapeamento['uc'].get('nome')} ({mapeamento['uc'].get('sigla', '')})")
    if descartado:
        print("\nDescartado por não existir nos dados (a IA inventou ou errou):")
        for d in descartado:
            print(f"  - {d}")
    return input("\nUsar este mapeamento? [S/n] ").strip().lower() not in ("n", "nao", "não")


def main() -> None:
    from agente import ModeloOpenAI

    modelo = ModeloOpenAI(os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"), os.environ.get("LLM_MODELO", "qwen2.5:7b"),
                          os.environ.get("LLM_API_KEY", "sem-chave"))
    no_terminal = sys.stdin.isatty()
    try:
        rel = importar_com_ia(RAIZ / "dados", modelo, _perguntar_no_terminal if no_terminal else None,
                              _confirmar_no_terminal if no_terminal else None)
    except ErroImportacao as erro:
        sys.exit(f"\nERRO: {erro}\n")
    except Exception as erro:  # IA fora do ar, por exemplo
        sys.exit(f"\nERRO ao falar com a IA ({modelo.base_url}, modelo {modelo.nome}): {erro}\n"
                 "O Ollama está rodando? Para importar sem IA, use `make`.\n")
    print(f"\nUC: {rel['uc']['nome']} | EPSG:{rel['epsg']}")
    for nome, fonte in rel["camadas"].items():
        print(f"  {nome:22s} <- {fonte}")
    for aviso in rel["avisos"]:
        print(f"  aviso: {aviso}")
    if rel["faltando"]:
        print("\nFALTA (coloque em dados/entrada/ e rode `make ia` de novo):")
        for item, consequencia in rel["faltando"]:
            print(f"  - {item}: sem isso, {consequencia}")


if __name__ == "__main__":
    main()
