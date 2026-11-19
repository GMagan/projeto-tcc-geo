#!/usr/bin/env python3
"""Importa os dados que o usuário colocou em dados/entrada/ e monta a base do projeto.

Tudo vem do usuário; nada é completado com dado de outro lugar. O que falta
é pedido: no terminal, o script pergunta o nome da UC e o que significa um
valor de zona que ele não conhece, e guarda as respostas em dados/entrada/
(uc.yaml e zonas.yaml) para não perguntar de novo. Camadas ausentes são
listadas com as ferramentas que ficam sem funcionar.

Arquivos aceitos em dados/entrada/ (nomes livres, subpastas valem):
  vetores  .shp (com .shx, .dbf e .prj), .gpkg, .geojson, .zip
  raster   .tif de uso e cobertura do solo; legenda opcional em .csv de mesmo nome
           (colunas: código, classe)
  uc.yaml        nome e sigla da UC                (perguntado se faltar)
  zonas.yaml     valor no shapefile -> sigla        (perguntado se preciso)
  gabarito.yaml  números publicados no plano, para comparação (opcional)

Como cada arquivo é reconhecido:
  zoneamento     coluna de texto com nomes ou siglas das zonas do roteiro do ICMBio
                 (feições "Zona de Amortecimento" viram a zona de amortecimento)
  limite         nome do arquivo com "limite" ou "perimetro"; sem ele, a união das zonas
  municípios     nome do arquivo com "municip"
  demais vetores viram camadas com o nome do arquivo (ex.: estradas.shp -> estradas)

Saída: dados/processados/base.gpkg e dados/catalogo.yaml, no fuso UTM (SIRGAS 2000)
da própria UC.

Uso:  python scripts/importar_dados.py      (o `make` já chama)
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Callable

import geopandas as gpd
import pandas as pd
import yaml
from shapely import make_valid
from shapely.ops import unary_union

RAIZ = Path(__file__).resolve().parents[1]

# As 14 zonas do Roteiro Metodológico do ICMBio (2018), mais a de amortecimento.
ZONAS = [  # (sigla, nome, trechos que identificam o nome)
    ("ZP", "Zona de Preservação", ("preserva",)),
    ("ZC", "Zona de Conservação", ("conserva",)),
    ("ZUR", "Zona de Uso Restrito", ("uso restrito",)),
    ("ZUM", "Zona de Uso Moderado", ("uso moderado",)),
    ("ZUC", "Zona de Uso Comunitário", ("uso comunitario",)),
    ("ZMF", "Zona de Manejo Florestal", ("manejo florestal",)),
    ("ZI", "Zona de Infraestrutura", ("infraestrutura", "infra-estrutura")),
    ("ZPO", "Zona Populacional", ("populacional",)),
    ("ZPR", "Zona de Produção", ("producao",)),
    ("ZUI", "Zona Urbano-industrial", ("urbano",)),
    ("ZST", "Zona de Sobreposição Territorial", ("sobreposicao",)),
    ("ZDIP", "Zona de Diferentes Interesses Públicos", ("interesse",)),
    ("ZAA", "Zona de Adequação Ambiental", ("adequacao",)),
    ("ZUD", "Zona de Uso Divergente", ("divergente",)),
    ("ZA", "Zona de Amortecimento", ("amortec",)),
]
NOME = {s: n for s, n, _ in ZONAS}
VETORES = (".shp", ".gpkg", ".geojson", ".zip")
RASTERS = (".tif", ".tiff")
CAMPOS_DE_NOME = ("nm_mun", "nome", "name", "municipio", "denominacao", "ref")


class ErroImportacao(RuntimeError):
    """Problema nos dados que o usuário precisa resolver; a mensagem diz como."""


Perguntar = Callable[..., str]


def _normalizar(texto) -> str:
    return " ".join(unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().casefold().split())


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _normalizar(texto)).strip("_") or "camada"


def classificar(valor, mapa: dict[str, str]) -> str | None:
    """'ZONA DE CONSERVAÇÃO', 'zc' ou um valor de zonas.yaml -> 'ZC'; desconhecido -> None."""
    texto = _normalizar(valor)
    if texto in mapa:
        return mapa[texto]
    if texto.upper() in NOME:
        return texto.upper()
    return next((s for s, _, trechos in ZONAS if any(t in texto for t in trechos)), None)


def epsg_utm(lon: float, lat: float) -> int:
    """EPSG do fuso UTM em SIRGAS 2000 que contém o ponto (31978 = 18S ... 31985 = 25S)."""
    fuso = int((lon + 180) // 6) + 1
    return (31960 if lat < 0 else 31954) + fuso


def _ler_vetor(arquivo: Path) -> gpd.GeoDataFrame:
    if arquivo.suffix.lower() == ".shp" and not any(arquivo.with_suffix(e).exists() for e in (".prj", ".PRJ")):
        raise ErroImportacao(f"{arquivo.name}: falta o arquivo {arquivo.stem}.prj (sistema de coordenadas). "
                             "Copie o shapefile completo: .shp, .shx, .dbf e .prj.")
    gdf = gpd.read_file(f"zip://{arquivo}" if arquivo.suffix.lower() == ".zip" else arquivo)
    if gdf.crs is None:
        raise ErroImportacao(f"{arquivo.name}: o arquivo não informa o sistema de coordenadas (CRS).")
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]


def _texto(gdf: gpd.GeoDataFrame) -> list[str]:
    return [c for c in gdf.columns if c != "geometry" and gdf[c].dtype.kind in "OSU"]


def _coluna_de_zona(gdf: gpd.GeoDataFrame, mapa: dict) -> str | None:
    """Coluna em que pelo menos metade das feições tem nome ou sigla de zona."""
    contagem = {c: sum(classificar(v, mapa) is not None for v in gdf[c].dropna()) for c in _texto(gdf)}
    melhor = max(contagem, key=contagem.get, default=None)
    return melhor if melhor and contagem[melhor] >= len(gdf) / 2 else None


def _campo_nome(gdf: gpd.GeoDataFrame) -> str | None:
    texto = _texto(gdf)
    return next((c for chave in CAMPOS_DE_NOME for c in texto if chave in _normalizar(c)), texto[0] if texto else None)


def _pedir_uc(entrada: Path, perguntar: Perguntar | None) -> dict:
    arquivo = entrada / "uc.yaml"
    if arquivo.exists():
        uc = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
        if uc.get("nome"):
            return {"nome": str(uc["nome"]), "sigla": str(uc.get("sigla") or "")}
    if perguntar is None:
        raise ErroImportacao(f"falta o nome da UC: crie {arquivo} com as linhas 'nome: ...' e 'sigla: ...'")
    uc = {"nome": perguntar("Nome da unidade de conservação"), "sigla": perguntar("Sigla da unidade (ex.: REBIO)")}
    arquivo.write_text(yaml.safe_dump(uc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return uc


def _pedir_zonas(valores: list[str], arquivo_origem: str, entrada: Path, mapa: dict, perguntar: Perguntar | None) -> None:
    """Pergunta a sigla de cada valor desconhecido e guarda em zonas.yaml."""
    if perguntar is None:
        raise ErroImportacao(
            f"{arquivo_origem}: valores que não são zona conhecida: {valores}. Crie {entrada / 'zonas.yaml'} dizendo a "
            f"sigla de cada um (ex.: '{valores[0]}: ZC'). Siglas: {', '.join(NOME)}")
    arquivo = entrada / "zonas.yaml"
    salvo = yaml.safe_load(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
    salvo = salvo or {}
    opcoes = [f"{s} = {n}" for s, n in NOME.items()]
    for valor in valores:
        while (sigla := perguntar(f"Qual zona é '{valor}' ({arquivo_origem})?", opcoes).strip().upper()) not in NOME:
            print(f"  '{sigla}' não é uma sigla válida")
        salvo[valor] = sigla
        mapa[_normalizar(valor)] = sigla
    arquivo.write_text(yaml.safe_dump(salvo, allow_unicode=True, sort_keys=False), encoding="utf-8")


def importar(pasta: Path, perguntar: Perguntar | None = None) -> dict:
    """Lê `pasta`/entrada e grava `pasta`/processados/base.gpkg e `pasta`/catalogo.yaml."""
    entrada = pasta / "entrada"
    entrada.mkdir(parents=True, exist_ok=True)
    if not any(p.suffix.lower() in VETORES for p in entrada.rglob("*")):
        raise ErroImportacao(f"{entrada} está vazia: coloque ali o shapefile do zoneamento da UC "
                             "(e, se tiver, limite, municípios, estradas, raster de uso do solo e gabarito.yaml)")
    uc = _pedir_uc(entrada, perguntar)
    mapa_yaml = entrada / "zonas.yaml"
    mapa = {_normalizar(k): str(v).upper() for k, v in (yaml.safe_load(mapa_yaml.read_text(encoding="utf-8")) or {}).items()} \
        if mapa_yaml.exists() else {}

    arquivos = sorted(p for p in entrada.rglob("*") if p.is_file() and not p.name.startswith("."))
    pecas: dict[str, list] = {}
    origem: dict[str, str] = {}
    limite, municipios, outras, rasters = [], None, {}, []
    for arquivo in arquivos:
        sufixo, nome = arquivo.suffix.lower(), _normalizar(arquivo.stem)
        if sufixo in RASTERS:
            rasters.append(arquivo)
            continue
        if sufixo not in VETORES:
            continue
        gdf = _ler_vetor(arquivo)
        if "limite" in nome or "perimetro" in nome:
            limite.append((arquivo.name, gdf))
        elif "municip" in nome:
            municipios = (arquivo.name, gdf)
        elif coluna := _coluna_de_zona(gdf, mapa):
            desconhecidos = sorted({str(v) for v in gdf[coluna].dropna() if classificar(v, mapa) is None})
            if desconhecidos:
                _pedir_zonas(desconhecidos, arquivo.name, entrada, mapa, perguntar)
            for valor, geom in zip(gdf[coluna], gdf.to_crs(4674).geometry):
                sigla = classificar(valor, mapa)
                if sigla:
                    pecas.setdefault(sigla, []).append(geom)
                    origem[sigla] = arquivo.name
        elif "zon" in nome:
            raise ErroImportacao(f"{arquivo.name}: parece o zoneamento, mas nenhuma coluna traz o nome ou a sigla das zonas. "
                                 f"Colunas: {_texto(gdf)}. Crie {mapa_yaml} dizendo a sigla de cada valor.")
        else:
            outras[_slug(arquivo.stem)] = (arquivo.name, gdf)

    internas = [s for s in NOME if s in pecas and s != "ZA"]
    if not internas:
        raise ErroImportacao(f"nenhum zoneamento encontrado em {entrada}: coloque ali o shapefile do zoneamento da UC")

    # fuso UTM da própria UC: medir no fuso errado distorce áreas
    centro = unary_union([g for s in internas for g in pecas[s]]).centroid
    epsg = epsg_utm(centro.x, centro.y)
    em_utm = lambda geoms: make_valid(gpd.GeoSeries(geoms, crs=4674).to_crs(epsg).union_all())  # noqa: E731

    zonas = {s: em_utm(pecas[s]) for s in internas}
    avisos, faltando, camadas = [], [], {}
    if limite:
        geom_limite = make_valid(unary_union([g.to_crs(epsg).union_all() for _, g in limite]))
        fonte_limite = ", ".join(n for n, _ in limite)
        fora = sum(z.difference(geom_limite).area for z in zonas.values())
        if fora > 0.01 * geom_limite.area:
            avisos.append(f"{fora / 1e4:.2f} ha de zonas ficam fora do limite da UC")
    else:
        geom_limite, fonte_limite = make_valid(unary_union(list(zonas.values()))), "união das zonas"
        avisos.append("sem arquivo de limite: o limite da UC é a união das zonas internas")
    sobreposicao = sum(z.area for z in zonas.values()) - unary_union(list(zonas.values())).area
    if sobreposicao > 1.0:  # 1 m²
        avisos.append(f"{sobreposicao / 1e4:.2f} ha de sobreposição entre zonas")

    def camada(gdf, fonte, **meta):
        return {"gdf": gdf, "fonte": fonte, **meta}

    camadas["limite_uc"] = camada(gpd.GeoDataFrame([{"nome": uc["nome"], "sigla": uc["sigla"]}], geometry=[geom_limite], crs=epsg),
                                  fonte_limite, descricao="Limite da UC.", campo_nome="nome")
    camadas["zoneamento"] = camada(gpd.GeoDataFrame([{"sigla": s, "zona": NOME[s]} for s in internas], geometry=list(zonas.values()), crs=epsg),
                                   ", ".join(sorted({origem[s] for s in internas})), descricao="Zonas de manejo internas.",
                                   campo_sigla="sigla", campo_nome="zona")
    if "ZA" in pecas:
        camadas["zona_amortecimento"] = camada(
            gpd.GeoDataFrame([{"sigla": "ZA", "zona": NOME["ZA"]}], geometry=[make_valid(em_utm(pecas["ZA"]).difference(geom_limite))], crs=epsg),
            origem["ZA"], descricao="Zona de Amortecimento (sem a área da UC).", campo_sigla="sigla", campo_nome="zona")
    else:
        faltando.append(("zona de amortecimento", "área e mapa da ZA; zona_da_coordenada não diz se um ponto está na ZA"))
    if municipios:
        nome_arq, gdf = municipios
        campo = _campo_nome(gdf)
        if campo is None:
            raise ErroImportacao(f"{nome_arq}: nenhuma coluna de texto com o nome dos municípios")
        gdf = gdf.to_crs(epsg).rename(columns={campo: "nome"})[["nome", "geometry"]]
        camadas["municipios"] = camada(gdf, nome_arq, descricao="Municípios.", campo_nome="nome")
    else:
        faltando.append(("municípios", "municipios_intersectados (municípios e percentuais da ficha técnica)"))
    for nome, (nome_arq, gdf) in outras.items():
        camadas[nome] = camada(gdf.to_crs(epsg), nome_arq, descricao=f"Camada fornecida: {nome_arq}.", campo_nome=_campo_nome(gdf))
    if not outras:
        faltando.append(("outras camadas (estradas, estruturas, hidrografia...)", "distancia_ate e intersecao só funcionam entre limite e zonas"))

    cat_rasters = {}
    uso = [r for r in rasters if any(k in _normalizar(r.stem) for k in ("uso", "cobertura", "mapbiomas"))] or rasters[:1]
    if uso:
        raster = uso[0]
        meta = {"arquivo": os.path.relpath(raster, pasta), "descricao": "Uso e cobertura do solo.", "fonte": raster.name, "provisorio": False}
        legenda = raster.with_suffix(".csv")
        if legenda.exists():
            tabela = pd.read_csv(legenda)
            meta["classes"] = {int(c): str(n) for c, n in zip(tabela.iloc[:, 0], tabela.iloc[:, 1])}
        else:
            avisos.append(f"{raster.name} sem legenda ({legenda.name}): as classes saem pelo código")
        cat_rasters["uso_solo"] = meta
        for extra in [r for r in rasters if r != raster]:
            avisos.append(f"{extra.name} ignorado: só um raster de uso do solo é usado")
    else:
        faltando.append(("uso do solo (raster .tif)", "uso_solo_na_area"))
    if not (entrada / "gabarito.yaml").exists():
        faltando.append(("gabarito.yaml", "a comparação com os números publicados no plano não é feita"))

    # grava do zero: camadas que o usuário removeu não podem sobrar
    base = pasta / "processados" / "base.gpkg"
    base.parent.mkdir(parents=True, exist_ok=True)
    base.unlink(missing_ok=True)
    catalogo = {"crs_trabalho": epsg, "uc": uc, "camadas": {}, "rasters": cat_rasters}
    if (entrada / "gabarito.yaml").exists():
        catalogo["gabarito"] = "entrada/gabarito.yaml"
    for nome, c in camadas.items():
        gdf = c["gdf"].copy()
        gdf["geometry"] = gdf.geometry.apply(make_valid)
        gdf.to_file(base, layer=nome, driver="GPKG")
        meta = {"arquivo": "processados/base.gpkg", "camada": nome, "descricao": c["descricao"], "fonte": c["fonte"], "provisorio": False}
        meta.update({k: c[k] for k in ("campo_sigla", "campo_nome") if c.get(k)})
        catalogo["camadas"][nome] = meta
    (pasta / "catalogo.yaml").write_text("# Gerado por scripts/importar_dados.py a partir de dados/entrada/: não edite.\n"
                                         + yaml.safe_dump(catalogo, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"uc": uc, "epsg": epsg, "camadas": {n: c["fonte"] for n, c in camadas.items()},
            "rasters": list(cat_rasters), "faltando": faltando, "avisos": avisos}


def _perguntar_no_terminal(pergunta: str, opcoes: list[str] | None = None) -> str:
    if opcoes:
        print("\n".join(f"    {o}" for o in opcoes))
    while not (resposta := input(f"{pergunta}: ").strip()):
        pass
    return resposta


def main() -> None:
    perguntar = _perguntar_no_terminal if sys.stdin.isatty() else None
    try:
        rel = importar(RAIZ / "dados", perguntar)
    except ErroImportacao as erro:
        sys.exit(f"\nERRO: {erro}\n")
    print(f"UC: {rel['uc']['nome']} ({rel['uc']['sigla']}) | sistema de referência: EPSG:{rel['epsg']} (SIRGAS 2000 / UTM)")
    for nome, fonte in rel["camadas"].items():
        print(f"  {nome:22s} <- {fonte}")
    for nome in rel["rasters"]:
        print(f"  {nome:22s} <- raster")
    for aviso in rel["avisos"]:
        print(f"  aviso: {aviso}")
    if rel["faltando"]:
        print("\nFALTA (coloque em dados/entrada/ e rode `make` de novo):")
        for item, consequencia in rel["faltando"]:
            print(f"  - {item}: sem isso, {consequencia}")


if __name__ == "__main__":
    main()
