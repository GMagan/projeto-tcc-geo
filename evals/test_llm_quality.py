"""Avaliação semântica das respostas do agente (LLM-as-a-Judge, DeepEval).

Lê os rastros gravados por `rodar_agente.py` e pede a um modelo juiz que
pontue cada resposta em três critérios: fidelidade cartográfica aos dados da
tool, aderência à persona e relevância. O juiz determinístico
(`juiz_numerico.py`) cobre a fidelidade numérica sem custo; este arquivo cobre
o que depende de leitura: tom, citação da fonte e pertinência.

Configuração (variáveis de ambiente):
  JUIZ_MODELO     modelo juiz no Ollama (ex.: qwen2.5:14b); sem ela, os testes são pulados
  JUIZ_BASE_URL   endereço do Ollama (padrão http://localhost:11434)
  RASTROS         arquivo .jsonl a avaliar (padrão: o mais recente em resultados/llm/*/agente.jsonl)

Uso:  JUIZ_MODELO=qwen2.5:14b pytest evals/test_llm_quality.py -m llm
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

deepeval = pytest.importorskip("deepeval", reason="pip install deepeval")
from deepeval import assert_test  # noqa: E402
from deepeval.metrics import AnswerRelevancyMetric, GEval  # noqa: E402
from deepeval.models import OllamaModel  # noqa: E402
from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: E402

pytestmark = pytest.mark.llm
RAIZ = Path(__file__).resolve().parents[1]


def _rastros() -> list[dict]:
    caminho = os.environ.get("RASTROS")
    if not caminho:
        candidatos = sorted((RAIZ / "resultados" / "llm").glob("*/agente.jsonl"), key=lambda p: p.stat().st_mtime)
        caminho = candidatos[-1] if candidatos else None
    if not caminho or not Path(caminho).exists():
        return []
    return [json.loads(l) for l in Path(caminho).read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.fixture(scope="module")
def juiz():
    modelo = os.environ.get("JUIZ_MODELO")
    if not modelo:
        pytest.skip("defina JUIZ_MODELO para rodar a avaliação com modelo juiz")
    return OllamaModel(model=modelo, base_url=os.environ.get("JUIZ_BASE_URL", "http://localhost:11434"), temperature=0)


@pytest.mark.parametrize("linha", _rastros() or [pytest.param(None, marks=pytest.mark.skip(reason="sem rastros: rode evals/rodar_agente.py"))], ids=lambda l: l["id"] if l else "sem-rastros")
def test_qualidade_da_resposta_do_agente(linha, juiz):
    rastro = linha["rastro"]
    caso = LLMTestCase(
        input=rastro["pergunta"],
        actual_output=rastro["resposta"],
        retrieval_context=[json.dumps(c["resultado"], ensure_ascii=False) for c in rastro["chamadas"]] or ["(nenhuma tool foi chamada)"],
    )
    fidelidade_cartografica = GEval(
        name="Fidelidade Cartográfica aos Dados",
        criteria=(
            "A resposta deve conter EXATAMENTE os valores numéricos (áreas, distâncias, percentuais, coordenadas) "
            "presentes no Retrieval Context, que é o retorno das tools. A resposta não pode deduzir, arredondar de "
            "forma divergente nem criar medidas que não estejam no contexto."
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        model=juiz, threshold=0.9,
    )
    aderencia_a_persona = GEval(
        name="Aderência à Persona",
        criteria=(
            "A resposta deve citar a unidade de medida, a tool de origem do número e o sistema de referência "
            "(SIRGAS 2000 / UTM ou o EPSG informado em crs_calculo). Se o Retrieval Context indicar provisorio=true, a resposta deve "
            "avisar que o dado é provisório. O tom deve ser técnico e direto, sem parecer jurídico."
        ),
        evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        model=juiz, threshold=0.7,
    )
    relevancia = AnswerRelevancyMetric(model=juiz, threshold=0.8)
    assert_test(caso, [fidelidade_cartografica, aderencia_a_persona, relevancia])
