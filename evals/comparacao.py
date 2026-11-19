"""Comparação entre os números calculados e os publicados no plano de manejo.

O gabarito é do usuário (dados/entrada/gabarito.yaml) e todas as chaves são
opcionais; só o que vier é comparado:

    area_uc_ha: 616.86
    perimetro_km: 13.77
    municipios_percentual: {Candói: 51, Pinhão: 32}
    extremos: {norte_lat: "25° 37' 46,846\\"", oeste_lon: "51° 59' 22,879\\""}
    zonas_ha: {ZC: 538.37, ZAA: 70.42}
    zona_amortecimento_ha: 1622.48

Tolerância: meia unidade da última casa decimal publicada (616.86 -> 0,005;
51 -> 0,5), isto é, o valor calculado, arredondado como no plano, tem de dar o
número publicado.
"""
from __future__ import annotations

import re

import yaml

import geotools as gt
from geotools.catalogo import _normalizar


class _Publicado(float):
    """Número do gabarito que lembra como foi escrito: 1622.50 tem 2 casas, mesmo valendo 1622.5."""


class _LeitorGabarito(yaml.SafeLoader):
    pass


def _ler_numero(leitor, no):
    numero = _Publicado(leitor.construct_yaml_float(no))
    numero.texto = no.value
    return numero


_LeitorGabarito.add_constructor("tag:yaml.org,2002:float", _ler_numero)


def ler_gabarito(texto: str) -> dict | None:
    return yaml.load(texto, Loader=_LeitorGabarito)


def carregar_gabarito(cat: gt.Catalogo) -> dict | None:
    caminho = (yaml.safe_load(cat.caminho.read_text(encoding="utf-8")) or {}).get("gabarito")
    return ler_gabarito((cat.pasta / caminho).read_text(encoding="utf-8")) if caminho else None


def _meia_unidade(valor) -> float:
    texto = getattr(valor, "texto", str(valor)).replace(",", ".")
    casas = len(texto.split(".")[1]) if "." in texto else 0
    return 0.5 * 10**-casas


class ErroGabarito(ValueError):
    """gabarito.yaml escrito de um jeito que a comparação não entende; a mensagem diz como corrigir."""


def _segundos(valor) -> tuple[float, float]:
    """'25° 37' 46,846\"' ou -25.6297 (graus decimais) -> (segundos de arco, tolerância pelas casas publicadas)."""
    if isinstance(valor, (int, float)):
        return abs(float(valor)) * 3600, _meia_unidade(valor) * 3600
    partes = re.findall(r"\d+(?:[,.]\d+)?", str(valor))
    if len(partes) != 3:
        raise ErroGabarito(f"extremo '{valor}': use graus, minutos e segundos (\"25° 37' 46,846\\\"\") ou graus decimais (-25.6297)")
    g, m, s = partes
    return float(g) * 3600 + float(m) * 60 + float(s.replace(",", ".")), _meia_unidade(s)


def comparar(cat: gt.Catalogo, gabarito: dict | None) -> list[dict]:
    """Uma linha por número do gabarito: publicado, calculado, erro e se bate."""
    if not gabarito:
        return []
    linhas = []

    def linha(grandeza: str, unidade: str, plano: float, calculado: float | None, tolerancia: float, tool: str) -> None:
        if isinstance(plano, bool) or not isinstance(plano, (int, float)):
            raise ErroGabarito(f"{grandeza}: '{plano}' não é número; escreva com ponto decimal, sem milhar (ex.: 1622.50)")
        erro = None if calculado is None else round(calculado - plano, 4)
        linhas.append({
            "grandeza": grandeza, "unidade": unidade, "plano": plano, "plataforma": calculado, "erro": erro,
            "erro_percentual": round(100 * erro / plano, 2) if erro is not None and plano else None,
            "tolerancia": round(tolerancia, 6), "dentro_da_tolerancia": erro is not None and abs(erro) <= tolerancia + 1e-9,
            "tool": tool,
        })

    if "area_uc_ha" in gabarito or "perimetro_km" in gabarito:
        uc = gt.calcular_area(cat, "limite_uc")
        if "area_uc_ha" in gabarito:
            linha("Área da UC", "ha", gabarito["area_uc_ha"], uc["area_ha"], _meia_unidade(gabarito["area_uc_ha"]), "calcular_area")
        if "perimetro_km" in gabarito:
            linha("Perímetro da UC", "km", gabarito["perimetro_km"], uc["perimetro_km"], _meia_unidade(gabarito["perimetro_km"]), "calcular_area")

    if gabarito.get("municipios_percentual"):
        calc = {_normalizar(m["municipio"]): m["percentual"] for m in gt.municipios_intersectados(cat)["municipios"]} \
            if "municipios" in cat.camadas else {}
        for nome, pct in gabarito["municipios_percentual"].items():
            linha(f"Parcela da UC em {nome}", "%", pct, calc.get(_normalizar(nome)), _meia_unidade(pct), "municipios_intersectados")

    if gabarito.get("extremos"):
        ext = gt.coordenadas_extremas(cat, "limite_uc")
        for chave, texto in gabarito["extremos"].items():
            ponto, _, eixo = str(chave).partition("_")
            if ponto not in ("norte", "sul", "leste", "oeste") or eixo not in ("lat", "lon"):
                raise ErroGabarito(f"extremos.{chave}: a chave deve ser <norte|sul|leste|oeste>_<lat|lon>, ex.: norte_lat")
            plano, tol = _segundos(texto)
            nome_eixo = "latitude" if eixo == "lat" else "longitude"
            linha(f"Extremo {ponto} ({nome_eixo})", "segundos de arco", round(plano, 3), round(abs(ext[ponto][eixo]) * 3600, 3), tol, "coordenadas_extremas")

    if gabarito.get("zonas_ha"):
        calc = {_normalizar(z["sigla"]): z["area_ha"] for z in gt.calcular_area_zonas(cat)["zonas"]}
        for sigla, area in gabarito["zonas_ha"].items():
            linha(f"Área da {sigla}", "ha", area, calc.get(_normalizar(sigla)), _meia_unidade(area), "calcular_area_zonas")

    if "zona_amortecimento_ha" in gabarito:
        za = gt.calcular_area(cat, "zona_amortecimento")["area_ha"] if "zona_amortecimento" in cat.camadas else None
        linha("Área da Zona de Amortecimento", "ha", gabarito["zona_amortecimento_ha"], za,
              _meia_unidade(gabarito["zona_amortecimento_ha"]), "calcular_area")
    return linhas
