"""Consulta ao roteiro metodológico: recuperação lexical BM25, determinística e auditável.

O roteiro do ICMBio entra no sistema como *controle* (IDEF0): o agente consulta
o trecho normativo em vez de recitá-lo de memória. BM25 foi preferido a
embeddings porque dispensa um segundo modelo, repete o mesmo resultado a cada
execução e deixa visível por que um trecho foi escolhido (os termos em comum).
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

PALAVRAS_VAZIAS = frozenset(
    "a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sob sobre entre e ou que se "
    "como mais menos ao aos à às é são ser foi será está estão ter tem têm qual quais quando onde seu sua seus "
    "suas este esta estes estas esse essa isso aquele aquela ele ela eles elas não sim também já pelo pela pelos "
    "pelas the of and".split()
)


def tokenizar(texto: str) -> list[str]:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().casefold()
    return [t for t in re.findall(r"[a-z0-9]+", sem_acento) if len(t) > 1 and t not in _VAZIAS_SEM_ACENTO]


_VAZIAS_SEM_ACENTO = frozenset(
    unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode() for p in PALAVRAS_VAZIAS
)


class IndiceBM25:
    """Okapi BM25 sobre uma lista de trechos {fonte, pagina, texto}."""

    def __init__(self, trechos: list[dict], k1: float = 1.5, b: float = 0.75):
        self.trechos = trechos
        self.k1, self.b = k1, b
        self._tf = [Counter(tokenizar(t["texto"])) for t in trechos]
        self._tam = [sum(tf.values()) for tf in self._tf]
        self._media = (sum(self._tam) / len(self._tam)) if trechos else 0.0
        df = Counter(termo for tf in self._tf for termo in tf)
        n = len(trechos)
        self._idf = {termo: math.log(1 + (n - d + 0.5) / (d + 0.5)) for termo, d in df.items()}

    @classmethod
    def de_jsonl(cls, caminho: str | Path) -> "IndiceBM25":
        linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
        return cls([json.loads(l) for l in linhas if l.strip()])

    def buscar(self, consulta: str, k: int = 3) -> list[tuple[float, dict]]:
        termos = tokenizar(consulta)
        pontuados = []
        for tf, tam, trecho in zip(self._tf, self._tam, self.trechos):
            pontos = 0.0
            for termo in termos:
                f = tf.get(termo, 0)
                if f:
                    pontos += self._idf[termo] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * tam / self._media))
            if pontos > 0:
                pontuados.append((pontos, trecho))
        pontuados.sort(key=lambda par: -par[0])
        return pontuados[:k]


def consultar_roteiro(indice: IndiceBM25, consulta: str, k: int = 3) -> dict:
    """Trechos do roteiro mais relacionados à consulta, com fonte e página para citação."""
    k = max(1, min(int(k), 8))
    return {
        "status": "sucesso",
        "ferramenta": "consultar_roteiro",
        "consulta": consulta,
        "trechos": [
            {"fonte": t.get("fonte", ""), "pagina": t.get("pagina"), "pontuacao": round(p, 3), "texto": t["texto"]}
            for p, t in indice.buscar(consulta, k)
        ],
        "metodo": "BM25 (k1=1,5; b=0,75) sobre o texto do roteiro, um trecho por página",
    }
