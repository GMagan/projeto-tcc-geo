#!/usr/bin/env python3
"""Monta a base de conhecimento do agente a partir do Roteiro Metodológico do ICMBio (2018).

Extrai o texto do PDF página a página, limpa cabeçalhos e hifenização de fim
de linha e grava um trecho por página em conhecimento/roteiro_icmbio_2018.jsonl.
Cada trecho guarda a página, para que o agente cite a fonte do que afirmar.

Uso:  python scripts/construir_rag.py --pdf caminho/do/roteiro.pdf  (só para refazer conhecimento/)
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parents[1]
FONTE = "ICMBio (2018), Roteiro Metodológico para Elaboração e Revisão de Planos de Manejo das UCs Federais"
CABECALHO = re.compile(
    r"ROTEIRO METODOLÓGICO PARA ELABORAÇÃO E REVISÃO DE PLANOS DE MANEJO DAS UNIDADES DE CONSERVAÇÃO FEDERAIS", re.I
)
MIN_CARACTERES = 200  # capas e páginas só com figura ficam de fora


def limpar(texto: str) -> str:
    texto = CABECALHO.sub(" ", texto)
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)  # "conser-\nvação" -> "conservação"
    texto = re.sub(r"\bz\s*\n\s*z\s*\n", "• ", texto)  # marcadores de lista viram "z z" na extração
    texto = re.sub(r"\s*\n\s*", " ", texto)
    texto = re.sub(r"^\s*\d{1,3}\s+|\s+\d{1,3}\s*$", " ", texto)  # número da página nas bordas
    return re.sub(r"\s{2,}", " ", texto).strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pdf", type=Path, required=True, help="PDF do roteiro do ICMBio (2018)")
    ap.add_argument("--saida", type=Path, default=RAIZ / "conhecimento" / "roteiro_icmbio_2018.jsonl")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    trechos = []
    for numero, pagina in enumerate(doc, start=1):  # no roteiro, a página impressa coincide com a do PDF
        texto = limpar(pagina.get_text("text"))
        if len(texto) >= MIN_CARACTERES:
            trechos.append({"fonte": FONTE, "pagina": numero, "texto": texto})
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in trechos) + "\n", encoding="utf-8")
    print(f"{len(trechos)} trechos de {doc.page_count} páginas -> {args.saida.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
