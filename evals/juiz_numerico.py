"""Juiz determinístico de fidelidade numérica.

Responde, sem modelo de linguagem, se cada número da resposta do agente veio
de uma tool (ou da própria pergunta). Complementa o juiz LLM (DeepEval): é
barato, reproduzível e não alucina.

Regras:
  * identificadores não são medidas e saem antes da análise: nomes de CRS
    (SIRGAS 2000, UTM 20S, EPSG:31980, GRS80) e números de leis e decretos;
  * inteiros de 0 a 10 sem unidade são tratados como enumeração ("as 4 zonas", "1)");
    com unidade ("8 ha", "5 km", "10%") contam como medida;
  * um número é fiel se coincide com algum número devolvido por tool, citado
    em texto de tool (página do roteiro, por exemplo) ou presente na pergunta;
  * número que só coincide depois de arredondado conta como infiel e é
    listado à parte: a persona manda copiar, não arredondar.
"""
from __future__ import annotations

import re

IDENTIFICADORES = re.compile(
    r"SIRGAS\s*2000|UTM\s*(?:fuso\s*)?\d{1,2}\s*[SN]?\b|fuso\s*\d{1,2}\s*[SN]?\b|EPSG\s*:?\s*\d+|GRS\s*-?\s*80"
    r"|(?:Lei|Decreto|Portaria|Resolu[çc][ãa]o|Instru[çc][ãa]o Normativa)[^.;\n]{0,40}?n?[º°o.]*\s*[\d.]+(?:/\d{2,4})?",
    re.IGNORECASE,
)
NUMERO = re.compile(r"(?<![\w.,])-?\d+(?:[.,]\d+)*(?![\w])")
UNIDADE = re.compile(r"\s*(?:%|°|(?:ha|hectares?|km²?|m²?|metros?|quil[ôo]metros?)\b)", re.IGNORECASE)
MILHAR_BR = re.compile(r"-?\d{1,3}(?:\.\d{3})+")


def _interpretacoes(token: str) -> list[float]:
    """Valores possíveis de um token numérico ('1.622' pode ser milhar ou decimal)."""
    if "," in token:  # padrão brasileiro: ponto é milhar, vírgula é decimal
        return [float(token.replace(".", "").replace(",", "."))]
    if MILHAR_BR.fullmatch(token):
        como_milhar = float(token.replace(".", ""))
        return [como_milhar, float(token)] if token.count(".") == 1 else [como_milhar]
    return [float(token)]


def _casas(token: str) -> int:
    if "," in token:
        return len(token.split(",")[1])
    if MILHAR_BR.fullmatch(token):
        return 0
    return len(token.split(".")[1]) if "." in token else 0


def _tokens(texto: str) -> list[str]:
    return [t.rstrip(".,") for t in NUMERO.findall(IDENTIFICADORES.sub(" ", texto)) if any(c.isdigit() for c in t)]


def extrair_numeros(texto: str) -> list[float]:
    """Números de um texto, na ordem; aceita 1.622,48, 616,66, 616.66 e -51.9750."""
    return [_interpretacoes(t)[0] for t in _tokens(texto)]


def _numeros_de(objeto) -> set[float]:
    """Todos os números de uma estrutura JSON, inclusive os escritos dentro de textos."""
    achados: set[float] = set()
    if isinstance(objeto, bool) or objeto is None:
        return achados
    if isinstance(objeto, (int, float)):
        achados.add(abs(float(objeto)))
    elif isinstance(objeto, str):
        for t in _tokens(objeto):
            achados.update(abs(v) for v in _interpretacoes(t))
    elif isinstance(objeto, dict):
        for valor in objeto.values():
            achados |= _numeros_de(valor)
    elif isinstance(objeto, (list, tuple)):
        for valor in objeto:
            achados |= _numeros_de(valor)
    return achados


def _igual(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def avaliar(resposta: str, rastro: dict, tools_esperadas: list[str] | None = None, valores_esperados: list[float] | None = None) -> dict:
    """Mede a fidelidade numérica de uma resposta em relação ao rastro da execução."""
    chamadas = rastro.get("chamadas", [])
    permitidos = _numeros_de(rastro.get("pergunta", ""))
    for chamada in chamadas:
        permitidos |= _numeros_de(chamada.get("resultado")) | _numeros_de(chamada.get("argumentos"))

    medidas, sem_origem, arredondados = [], [], []
    limpo = IDENTIFICADORES.sub(" ", resposta or "")
    for achado in NUMERO.finditer(limpo):
        token = achado.group().rstrip(".,")
        valores = [abs(v) for v in _interpretacoes(token)]
        if "," not in token and "." not in token and valores[0] <= 10 and not UNIDADE.match(limpo, achado.end()):
            continue  # enumeração ("as 4 zonas", "1)"); com unidade ("8 ha") é medida
        medidas.append(_interpretacoes(token)[0])
        if any(_igual(v, p) for v in valores for p in permitidos):
            continue
        sem_origem.append(_interpretacoes(token)[0])
        casas = _casas(token)
        if any(_igual(valores[0], round(p, casas)) for p in permitidos):
            arredondados.append(_interpretacoes(token)[0])

    usadas = [c["tool"] for c in chamadas]
    na_resposta = [abs(v) for t in _tokens(resposta or "") for v in _interpretacoes(t)]
    houve_provisorio = any(isinstance(c.get("resultado"), dict) and c["resultado"].get("provisorio") for c in chamadas)
    return {
        "n_numeros": len(medidas),
        "n_fieis": len(medidas) - len(sem_origem),
        "fidelidade": round((len(medidas) - len(sem_origem)) / len(medidas), 4) if medidas else None,
        "numeros_sem_origem": sem_origem,
        "numeros_arredondados": arredondados,
        "alucinacao_numerica": bool(sem_origem),
        "chamou_tool": bool(chamadas),
        "tools_usadas": usadas,
        "usou_tool_esperada": all(t in usadas for t in tools_esperadas) if tools_esperadas is not None else None,
        "acertou_valores": all(any(_igual(abs(e), n) for n in na_resposta) for e in valores_esperados) if valores_esperados is not None else None,
        "citou_crs": bool(re.search(r"SIRGAS|EPSG\s*:?\s*\d{4,5}|UTM", resposta or "", re.IGNORECASE)),
        "avisou_provisorio": bool(re.search(r"provis[óo]ri", resposta or "", re.IGNORECASE)) if houve_provisorio else None,
    }
