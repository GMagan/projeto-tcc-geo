#!/usr/bin/env python3
"""Importa os dados que o usuário colocou em dados/entrada/ e monta a base do projeto.

Tudo vem do usuário; nada é completado com dado de outro lugar. O que falta
é pedido: no terminal, o script pergunta o nome da UC e o que significa um
valor de zona que ele não conhece, e guarda as respostas em dados/entrada/
(uc.yaml e zonas.yaml) para não perguntar de novo. Camadas ausentes são
listadas com as ferramentas que ficam sem funcionar.

Arquivos aceitos em dados/entrada/ (nomes livres, subpastas valem):
  vetores  .shp (com .shx, .dbf e .prj), .gpkg, .geojson, .zip
  raster   .tif de uso e cobertura do solo ("uso", "cobertura" ou "mapbiomas" no nome); legenda opcional em .csv de mesmo nome
           (colunas: código, classe)
  uc.yaml        nome e sigla da UC                (perguntado se faltar)
  zonas.yaml     valor no shapefile -> sigla        (perguntado se preciso)
  gabarito.yaml  números publicados no plano, para comparação (opcional)

Como cada arquivo é reconhecido:
  zoneamento     arquivo com "zon" ou "amortec" no nome e uma coluna de texto com nomes ou siglas das zonas
                 (feições "Zona de Amortecimento" viram a zona de amortecimento)
  limite         nome do arquivo com "limite" ou "perimetro" (e sem "municip"); sem ele, a união das zonas
  GeoPackage com várias camadas: cada camada conta como um arquivo, pelo nome da camada
  municípios     nome do arquivo com "municip"
  demais vetores viram camadas com o nome do arquivo (ex.: estradas.shp -> estradas)

Saída: dados/processados/base.gpkg e dados/catalogo.yaml, no fuso UTM (SIRGAS 2000)
da própria UC.

Uso:  python scripts/importar_dados.py      (o `make` já chama)
"""
from __future__ import annotations

import io
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Callable

import geopandas as gpd
import pandas as pd
import yaml
from pyproj import CRS
from pyproj.exceptions import CRSError
from shapely import make_valid
from shapely.geometry import box
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
    ("ZDIP", "Zona de Diferentes Interesses Públicos", ("interesses publicos", "interesse publico")),  # só "interesse" pegaria "Interesse Histórico"
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


def como_texto(valor) -> str:
    """Valor de atributo como texto; 3.0 vira '3' (coluna inteira com nulo é lida como decimal)."""
    return str(int(valor)) if isinstance(valor, float) and valor.is_integer() else str(valor)


def _normalizar(texto) -> str:
    return " ".join(unicodedata.normalize("NFKD", como_texto(texto)).encode("ascii", "ignore").decode().casefold().split())


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
    epsg = (31960 if lat < 0 else 31954) + fuso
    esperado = f"SIRGAS 2000 / UTM zone {fuso}{'S' if lat < 0 else 'N'}"
    # a série só cobre 11N-22N e 17S-25S; fora dela o código é de outro datum e fuso (Trindade, 26S -> 31986)
    try:
        nome = CRS.from_epsg(epsg).name
    except CRSError:
        nome = None
    if nome != esperado:
        raise ErroImportacao(f"a UC fica no fuso {fuso}{'S' if lat < 0 else 'N'}, que não tem código EPSG em SIRGAS 2000")
    return epsg


def listar_vetores(entrada: Path) -> list[tuple[str, Path, str | None]]:
    """(chave, arquivo, camada) de cada vetor em entrada/.

    GeoPackage com várias camadas (projeto salvo no QGIS) e .zip com vários shapefiles viram uma
    entrada por camada, com chave 'arquivo.gpkg/camada'; sem isso só a primeira seria lida.
    """
    itens = []
    for p in sorted(entrada.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in VETORES:
            continue
        rel = p.relative_to(entrada).as_posix()
        sufixo = p.suffix.lower()
        camadas = gpd.list_layers(f"zip://{p}" if sufixo == ".zip" else p)["name"].tolist() if sufixo in (".gpkg", ".zip") else []
        itens += [(f"{rel}/{c}", p, c) for c in camadas] if len(camadas) > 1 else [(rel, p, None)]
    return itens


def _ler_vetor(arquivo: Path, camada: str | None = None) -> gpd.GeoDataFrame:
    if arquivo.suffix.lower() == ".shp" and not any(arquivo.with_suffix(e).exists() for e in (".prj", ".PRJ")):
        raise ErroImportacao(f"{arquivo.name}: falta o arquivo {arquivo.stem}.prj (sistema de coordenadas). "
                             "Copie o shapefile completo: .shp, .shx, .dbf e .prj.")
    gdf = gpd.read_file(f"zip://{arquivo}" if arquivo.suffix.lower() == ".zip" else arquivo, layer=camada)
    if gdf.crs is None:
        raise ErroImportacao(f"{arquivo.name}: o arquivo não informa o sistema de coordenadas (CRS).")
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]


def _ler_legenda(caminho: Path) -> pd.DataFrame:
    """CSV com ',' ou ';' em UTF-8 ou cp1252: o Excel em português grava com ';' e em cp1252."""
    bruto = caminho.read_bytes()
    try:
        texto = bruto.decode("utf-8-sig")  # -sig tira a marca BOM do "CSV UTF-8" do Excel
    except UnicodeDecodeError:
        texto = bruto.decode("cp1252")
    cabecalho = texto.partition("\n")[0]
    return pd.read_csv(io.StringIO(texto), sep=";" if cabecalho.count(";") > cabecalho.count(",") else ",")


def _texto(gdf: gpd.GeoDataFrame) -> list[str]:
    return [c for c in gdf.columns if c != "geometry" and gdf[c].dtype.kind in "OSU"]


def _coluna_de_zona(gdf: gpd.GeoDataFrame, mapa: dict) -> str | None:
    """Coluna em que pelo menos metade das feições tem nome ou sigla de zona."""
    # todas as colunas: código numérico (COD_ZONA = 1, 2...) só casa quando zonas.yaml o traduz
    contagem = {c: sum(classificar(v, mapa) is not None for v in gdf[c].dropna()) for c in gdf.columns if c != "geometry"}
    melhor = max(contagem, key=contagem.get, default=None)
    return melhor if melhor and contagem[melhor] >= len(gdf) / 2 else None


def parece_zoneamento(nome_arquivo: str) -> bool:
    """Só arquivo com "zon..." ou "amortec..." no nome é lido como zoneamento.

    Sem isso, qualquer camada com texto parecido ("Área de Preservação Permanente") viraria zona.
    """
    return re.search(r"(?<![a-z])zon|amortec", nome_arquivo) is not None


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


def importar(pasta: Path, perguntar: Perguntar | None = None, mapeamento: dict | None = None) -> dict:
    """Lê `pasta`/entrada e grava `pasta`/processados/base.gpkg e `pasta`/catalogo.yaml.

    `mapeamento` (opcional, vem do modo IA) diz o papel de cada arquivo, pelo caminho relativo a
    entrada/: {"arquivo.shp": {"papel": "zoneamento", "coluna_zona": "TIPO"}, ...}. Papéis:
    zoneamento, zona_amortecimento, limite, municipios (coluna_nome), uso_solo (legenda),
    camada (nome_camada) e ignorar. Arquivo fora do mapeamento segue as regras de nome.
    """
    papeis = (mapeamento or {}).get("arquivos", {})
    entrada = pasta / "entrada"
    entrada.mkdir(parents=True, exist_ok=True)
    if not any(p.suffix.lower() in VETORES for p in entrada.rglob("*")):
        raise ErroImportacao(f"{entrada} está vazia: coloque ali o shapefile do zoneamento da UC "
                             "(e, se tiver, limite, municípios, estradas, raster de uso do solo e gabarito.yaml)")
    uc = _pedir_uc(entrada, perguntar)
    mapa_yaml = entrada / "zonas.yaml"
    mapa = {_normalizar(k): str(v).upper() for k, v in (yaml.safe_load(mapa_yaml.read_text(encoding="utf-8")) or {}).items()} \
        if mapa_yaml.exists() else {}
    if invalidas := {k: v for k, v in mapa.items() if v not in NOME}:
        raise ErroImportacao(f"{mapa_yaml}: sigla que não existe {invalidas}. Siglas: {', '.join(NOME)}")

    pecas: dict[str, list] = {}
    origem: dict[str, str] = {}
    limite, municipios, outras, rasters, legendas, uso_escolhido = [], None, {}, [], {}, None
    sem_zona: list[tuple[str, list]] = []  # (arquivo, geometrias) de feições com a coluna de zona vazia
    renomeadas: list[str] = []

    def guardar_outra(nome_camada: str, rotulo: str, arquivo: Path, gdf) -> None:
        """Camada extra; nome repetido (estaduais/estradas e municipais/estradas) ganha o nome da pasta."""
        ocupados = outras.keys() | {"limite_uc", "zoneamento", "zona_amortecimento", "municipios"}
        livre, n = nome_camada, 2
        if livre in ocupados:
            livre = _slug(f"{arquivo.parent.name}_{nome_camada}")
        while livre in ocupados:
            livre, n = f"{nome_camada}_{n}", n + 1
        if livre != nome_camada:
            renomeadas.append(f"{rotulo}: já existe uma camada '{nome_camada}'; esta virou '{livre}'")
        outras[livre] = (rotulo, gdf)
    for arquivo in sorted(p for p in entrada.rglob("*") if p.suffix.lower() in RASTERS and not p.name.startswith(".")):
        papel = papeis.get(arquivo.relative_to(entrada).as_posix(), {})
        if papel.get("papel") != "ignorar":
            rasters.append(arquivo)
            if papel.get("papel") == "uso_solo":
                uso_escolhido = arquivo
                if papel.get("legenda"):
                    legendas[arquivo] = entrada / papel["legenda"]
    for chave, arquivo, camada_gpkg in listar_vetores(entrada):
        papel = papeis.get(chave, {})
        if papel.get("papel") == "ignorar":
            continue
        base = camada_gpkg or arquivo.stem  # numa camada de GeoPackage, as regras de nome olham o nome da camada
        nome, rotulo = _normalizar(base), (f"{arquivo.name}/{camada_gpkg}" if camada_gpkg else arquivo.name)
        gdf = _ler_vetor(arquivo, camada_gpkg)
        tipo = papel.get("papel")
        if tipo == "zona_amortecimento":
            pecas.setdefault("ZA", []).extend(gdf.to_crs(4674).geometry)
            origem["ZA"] = rotulo
        elif tipo == "camada":
            guardar_outra(_slug(papel.get("nome_camada") or base), rotulo, arquivo, gdf)
        elif tipo == "municipios" or (not tipo and "municip" in nome):  # antes de "limite": limites_municipais.shp
            municipios = (rotulo, gdf, papel.get("coluna_nome"))
        elif tipo == "limite" or (not tipo and ("limite" in nome or "perimetro" in nome)):
            limite.append((rotulo, gdf))
        elif coluna := (papel.get("coluna_zona") if tipo == "zoneamento" else
                        _coluna_de_zona(gdf, mapa) if parece_zoneamento(nome) else None):
            desconhecidos = sorted({como_texto(v) for v in gdf[coluna].dropna() if classificar(v, mapa) is None})
            if desconhecidos:
                _pedir_zonas(desconhecidos, rotulo, entrada, mapa, perguntar)
            vazias = []
            for valor, geom in zip(gdf[coluna], gdf.to_crs(4674).geometry):
                if pd.isna(valor) or not como_texto(valor).strip():
                    vazias.append(geom)
                elif sigla := classificar(valor, mapa):
                    pecas.setdefault(sigla, []).append(geom)
                    origem[sigla] = rotulo
            if vazias:
                sem_zona.append((rotulo, vazias))
        elif parece_zoneamento(nome):
            raise ErroImportacao(f"{rotulo}: parece o zoneamento, mas nenhuma coluna traz o nome ou a sigla das zonas. "
                                 f"Colunas: {[c for c in gdf.columns if c != 'geometry']}. Crie {mapa_yaml} dizendo a sigla de cada valor "
                                 "(ex.: '1: ZP' para uma coluna de códigos).")
        else:
            guardar_outra(_slug(base), rotulo, arquivo, gdf)

    internas = [s for s in NOME if s in pecas and s != "ZA"]
    if not internas:
        raise ErroImportacao(f"nenhum zoneamento encontrado em {entrada}: coloque ali o shapefile do zoneamento da UC")

    # fuso UTM da própria UC: medir no fuso errado distorce áreas
    centro = unary_union([g for s in internas for g in pecas[s]]).centroid
    epsg = epsg_utm(centro.x, centro.y)
    em_utm = lambda geoms: make_valid(gpd.GeoSeries(geoms, crs=4674).to_crs(epsg).union_all())  # noqa: E731

    zonas = {s: em_utm(pecas[s]) for s in internas}
    avisos, faltando, camadas = list(renomeadas), [], {}
    for rotulo, geoms in sem_zona:
        avisos.append(f"{len(geoms)} feição(ões) de {rotulo} sem nome de zona ficaram de fora ({em_utm(geoms).area / 1e4:.2f} ha): "
                      "preencha a coluna de zona no arquivo")
    if limite:
        geom_limite = make_valid(unary_union([g.to_crs(epsg).union_all() for _, g in limite]))
        fonte_limite = ", ".join(n for n, _ in limite)
        fora = sum(z.difference(geom_limite).area for z in zonas.values())
        if fora > 0.01 * geom_limite.area:
            avisos.append(f"{fora / 1e4:.2f} ha de zonas ficam fora do limite da UC")
        # o zoneamento cobre a UC inteira: sobra grande é arquivo de limite errado (ex.: limite_za.shp)
        sobra = geom_limite.difference(unary_union(list(zonas.values()))).area
        if sobra > 0.01 * geom_limite.area:
            avisos.append(f"{sobra / 1e4:.2f} ha do limite da UC sem zona: confira se {fonte_limite} é mesmo o limite da UC")
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
        nome_arq, gdf, campo = municipios
        campo = campo or _campo_nome(gdf)
        if campo is None:
            raise ErroImportacao(f"{nome_arq}: nenhuma coluna de texto com o nome dos municípios")
        gdf = gdf.to_crs(epsg).rename(columns={campo: "nome"})[["nome", "geometry"]]
        # malha do Brasil inteiro (5.570 municípios): guarda só os vizinhos que aparecem no mapa
        x0, y0, x1, y1 = unary_union([geom_limite, *(c["gdf"].geometry.iloc[0] for n, c in camadas.items() if n == "zona_amortecimento")]).bounds
        gdf = gdf[gdf.intersects(box(x0, y0, x1, y1).buffer(max(x1 - x0, y1 - y0) / 2))]
        camadas["municipios"] = camada(gdf, nome_arq, descricao="Municípios.", campo_nome="nome")
    else:
        faltando.append(("municípios", "municipios_intersectados (municípios e percentuais da ficha técnica)"))
    for nome, (nome_arq, gdf) in outras.items():
        camadas[nome] = camada(gdf.to_crs(epsg), nome_arq, descricao=f"Camada fornecida: {nome_arq}.", campo_nome=_campo_nome(gdf))
    if not outras:
        faltando.append(("outras camadas (estradas, estruturas, hidrografia...)", "distancia_ate e intersecao só funcionam entre limite e zonas"))

    cat_rasters = {}
    uso = [uso_escolhido] if uso_escolhido else \
        [r for r in rasters if any(k in _normalizar(r.stem) for k in ("uso", "cobertura", "mapbiomas"))]
    if uso:
        raster = uso[0]
        meta = {"arquivo": os.path.relpath(raster, pasta), "descricao": "Uso e cobertura do solo.", "fonte": raster.name, "provisorio": False}
        legenda = legendas.get(raster, raster.with_suffix(".csv"))
        if legenda.exists():
            tabela = _ler_legenda(legenda)
            try:
                meta["classes"] = {int(c): str(n) for c, n in zip(tabela.iloc[:, 0], tabela.iloc[:, 1], strict=True)}
            except (IndexError, ValueError) as erro:
                raise ErroImportacao(f"{legenda.name}: a legenda precisa de duas colunas, código (número) e classe; "
                                     f"colunas lidas: {list(tabela.columns)}") from erro
        else:
            avisos.append(f"{raster.name} sem legenda ({legenda.name}): as classes saem pelo código")
        cat_rasters["uso_solo"] = meta
    else:
        faltando.append(("uso do solo (raster .tif)", "uso_solo_na_area"))
    for extra in [r for r in rasters if r not in uso[:1]]:
        avisos.append(f"{extra.name} ignorado: o raster de uso do solo precisa de 'uso', 'cobertura' ou 'mapbiomas' no nome "
                      "(e só um é usado)")
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
