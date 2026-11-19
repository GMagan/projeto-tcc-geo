#!/usr/bin/env python3
"""Baixa os dados abertos usados enquanto os shapefiles oficiais não chegam.

Cada fonte vai para uma pasta própria em dados/brutos/ e fica registrada em
dados/brutos/PROVENIENCIA.json (URL, data, tamanho, SHA-256 e licença), para
que qualquer número da monografia possa ser rastreado até o arquivo de origem.

Uso:  python scripts/baixar_dados.py            (pula o que já existe)
      python scripts/baixar_dados.py --forcar   (baixa tudo de novo)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
BRUTOS = RAIZ / "dados" / "brutos"
AGENTE = {"User-Agent": "projeto-tcc-geo/0.1 (pesquisa academica)"}

# Retângulo de trabalho (lat/lon) em torno do PESC, com folga para a zona de amortecimento.
SUL, OESTE, NORTE, LESTE = -25.72, -52.06, -25.58, -51.88

CONSULTA_OSM = f"""[out:json][timeout:90];
(
  way["highway"]({SUL},{OESTE},{NORTE},{LESTE});
  way["waterway"]({SUL},{OESTE},{NORTE},{LESTE});
  way["natural"="water"]({SUL},{OESTE},{NORTE},{LESTE});
  way["building"]({SUL},{OESTE},{NORTE},{LESTE});
  way["power"="line"]({SUL},{OESTE},{NORTE},{LESTE});
  node["tourism"]({SUL},{OESTE},{NORTE},{LESTE});
);
out body geom;"""
ESPELHOS_OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

FONTES = {
    "geobr_ucs": {
        "arquivo": "conservation_units_201909.gpkg",
        "url": "https://www.ipea.gov.br/geobr/data_gpkg/conservation_units/201909/conservation_units_201909.gpkg",
        "descricao": "Unidades de conservação do CNUC/MMA (set. 2019), redistribuídas pelo geobr/IPEA",
        "licença": "Dados públicos do MMA; pacote geobr sob licença MIT",
    },
    "ibge_municipios_pr": {
        "arquivo": "PR_Municipios_2024.zip",
        "url": "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
        "malhas_municipais/municipio_2024/UFs/PR/PR_Municipios_2024.zip",
        "descricao": "Malha municipal do Paraná, IBGE 2024 (escala 1:250.000)",
        "licença": "Dados públicos do IBGE, uso livre com citação da fonte",
    },
    "esa_worldcover": {
        "arquivo": "ESA_WorldCover_10m_2021_v200_S27W054_Map.tif",
        "url": "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
        "ESA_WorldCover_10m_2021_v200_S27W054_Map.tif",
        "descricao": "ESA WorldCover 10 m, 2021, v200 (recorte do retângulo de trabalho)",
        "licença": "CC BY 4.0 (ESA WorldCover project 2021)",
        "recorte": True,
    },
    "osm": {
        "arquivo": "overpass_pesc.json",
        "descricao": "OpenStreetMap: vias, hidrografia, edificações e pontos de interesse",
        "licença": "ODbL 1.0 (© colaboradores do OpenStreetMap)",
        "overpass": True,
    },
}


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar_arquivo(url: str, destino: Path) -> None:
    with requests.get(url, headers=AGENTE, stream=True, timeout=300) as r:
        r.raise_for_status()
        with destino.open("wb") as f:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)


def baixar_osm(destino: Path) -> str:
    ultimo_erro = None
    for espelho in ESPELHOS_OVERPASS:
        try:
            r = requests.post(espelho, data={"data": CONSULTA_OSM}, headers=AGENTE, timeout=180)
            r.raise_for_status()
            r.json()  # garante que veio JSON e não uma página de erro
            destino.write_bytes(r.content)
            return espelho
        except Exception as erro:  # tenta o próximo espelho
            ultimo_erro = erro
    raise RuntimeError(f"nenhum servidor Overpass respondeu: {ultimo_erro}")


def recortar_worldcover(url: str, destino: Path) -> None:
    """Lê só a janela do retângulo de trabalho (o arquivo inteiro tem ~100 MB)."""
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.windows import transform as transformar_janela

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(url) as origem:
            janela = from_bounds(OESTE, SUL, LESTE, NORTE, origem.transform).round_offsets().round_lengths()
            dados = origem.read(1, window=janela)
            perfil = origem.profile.copy()
            perfil.update(
                driver="GTiff",
                height=dados.shape[0],
                width=dados.shape[1],
                transform=transformar_janela(janela, origem.transform),
                compress="deflate",
                tiled=False,
            )
            perfil.pop("blockxsize", None)
            perfil.pop("blockysize", None)
            with rasterio.open(destino, "w", **perfil) as saida:
                saida.write(dados, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--forcar", action="store_true", help="baixa de novo o que já existe")
    args = ap.parse_args()

    registro_caminho = BRUTOS / "PROVENIENCIA.json"
    registro = json.loads(registro_caminho.read_text(encoding="utf-8")) if registro_caminho.exists() else {}

    for nome, fonte in FONTES.items():
        pasta = BRUTOS / nome
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / fonte["arquivo"]
        origem = fonte.get("url", "Overpass API")
        if destino.exists() and not args.forcar:
            print(f"[ok] {nome}: já existe")
        elif fonte.get("overpass"):
            origem = baixar_osm(destino)
            print(f"[baixado] {nome} de {origem}")
        elif fonte.get("recorte"):
            recortar_worldcover(fonte["url"], destino)
            print(f"[recortado] {nome}")
        else:
            baixar_arquivo(fonte["url"], destino)
            print(f"[baixado] {nome}")
        anterior = registro.get(nome, {})
        soma = sha256(destino)
        registro[nome] = {
            "arquivo": str(destino.relative_to(RAIZ)),
            "origem": origem if anterior.get("sha256") != soma else anterior.get("origem", origem),
            "descricao": fonte["descricao"],
            "licenca": fonte["licença"],
            "bytes": destino.stat().st_size,
            "sha256": soma,
            "obtido_em": anterior.get("obtido_em") if anterior.get("sha256") == soma else dt.date.today().isoformat(),
        }
        if nome == "osm":
            registro[nome]["consulta"] = CONSULTA_OSM
            registro[nome]["base_osm_em"] = json.loads(destino.read_text())["osm3s"]["timestamp_osm_base"]

    registro_caminho.write_text(json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"proveniência registrada em {registro_caminho.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
