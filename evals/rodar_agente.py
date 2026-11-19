#!/usr/bin/env python3
"""Roda o conjunto de perguntas contra um modelo de linguagem e grava rastros e métricas.

Duas condições:
  agente     persona + skill + tools MCP (a arquitetura proposta);
  sem_tools  só o modelo, com a geometria em WKT no prompt (linha de base).

Exemplos:
  python evals/rodar_agente.py --base-url http://localhost:11434/v1 --modelo qwen2.5:7b
  python evals/rodar_agente.py --base-url http://localhost:11434/v1 --modelo llama3.2:3b --condicao sem_tools

Saída: resultados/llm/<modelo>/<condicao>.jsonl (um rastro por pergunta) e resumo.json.
Com --apenas: <condicao>_parcial.jsonl, e resumo.json não muda.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "mcp-python"), str(RAIZ), str(RAIZ / "evals")]

import geotools as gt  # noqa: E402
import server  # noqa: E402
from agente import ModeloOpenAI, carregar_skill, executar  # noqa: E402
from juiz_numerico import avaliar  # noqa: E402

CHAVES_DE_LISTA = ("sigla", "municipio", "classe", "feicao")


def valor_no_caminho(resultado: dict, caminho: str):
    """'zonas.ZC.area_ha' -> resultado['zonas'][item com sigla ZC]['area_ha']."""
    atual = resultado
    for parte in caminho.split("."):
        if isinstance(atual, list):
            atual = next(item for item in atual if any(str(item.get(c)) == parte for c in CHAVES_DE_LISTA))
        else:
            atual = atual[parte]
    return atual


def valores_esperados(cat: gt.Catalogo, pergunta: dict) -> list[float]:
    """Gabarito de cada pergunta: a tool chamada direto, sem modelo no caminho."""
    valores = []
    for item in pergunta.get("esperado", []):
        funcao = getattr(gt, item["tool"])
        resultado = funcao(**item["args"]) if item["tool"] == "calcular_buffer_coordenada" else funcao(cat, **item["args"])
        valores += [float(valor_no_caminho(resultado, c)) for c in item.get("campos", [])]
    return valores


SKILL_DA_ZONA = {"ZC": "zona_conservacao", "ZAA": "zona_adequacao", "ZI": "zona_infraestrutura", "ZDIP": "zona_interesses_publicos"}
ZONAS_DO_ROTEIRO = ["Zona de Preservação", "Zona de Conservação", "Zona de Uso Restrito", "Zona de Uso Moderado",
                    "Zona de Infraestrutura", "Zona de Adequação Ambiental", "Zona de Diferentes Interesses Públicos"]


def gerar_perguntas(cat: gt.Catalogo) -> list[dict]:
    """Conjunto de avaliação montado a partir dos dados carregados (nada é fixo de uma UC)."""
    uc = cat.uc.get("nome") or "a UC"
    zonas = gt.percentual_por_zona(cat)["zonas"]
    maior = max(zonas, key=lambda z: z["area_ha"])
    tem = cat.camadas.__contains__
    P = []

    def q(ident, skill, pergunta, tools, esperado=(), geometria=None, **extra):
        P.append({"id": ident, "skill": skill, "pergunta": pergunta, "tools": list(tools), "esperado": list(esperado),
                  "geometria": geometria, **extra})

    def e(tool, args, campos):
        return {"tool": tool, "args": args, "campos": campos}

    q("area_uc", "ficha_tecnica", f"Qual é a área e o perímetro de {uc}?", ["calcular_area"],
      [e("calcular_area", {"camada": "limite_uc"}, ["area_ha", "perimetro_km"])], {"camada": "limite_uc"})
    q("extremos", "ficha_tecnica", "Qual é a latitude do ponto mais ao norte e a do ponto mais ao sul da UC, em graus decimais?",
      ["coordenadas_extremas"], [e("coordenadas_extremas", {"camada": "limite_uc"}, ["norte.lat", "sul.lat"])], {"camada": "limite_uc"})
    if tem("municipios"):
        nomes = [m["municipio"] for m in gt.municipios_intersectados(cat)["municipios"]]
        q("municipios", "ficha_tecnica", "Quais municípios a UC abrange e qual o percentual dela em cada um?", ["municipios_intersectados"],
          [e("municipios_intersectados", {"camada": "limite_uc"}, [f"municipios.{m}.percentual" for m in nomes])])
    q("tabela_zonas", "zoneamento", "Monte a tabela de zonas com a área em hectares e o percentual de cada uma.", ["percentual_por_zona"],
      [e("percentual_por_zona", {}, [f"zonas.{z['sigla']}.area_ha" for z in zonas] + [f"zonas.{z['sigla']}.percentual" for z in zonas])])
    q("total_zonas", "zoneamento", "Qual é a área total zoneada? Ela fecha com a área do limite da UC?", ["calcular_area_zonas"],
      [e("calcular_area_zonas", {}, ["total_ha", "area_limite_uc_ha"])])
    q("maior_zona", "zoneamento", "Qual zona ocupa a maior parte da UC e com que percentual?", ["percentual_por_zona"],
      [e("percentual_por_zona", {}, [f"zonas.{maior['sigla']}.percentual"])])
    for z in zonas:
        q(f"area_{z['sigla'].lower()}", SKILL_DA_ZONA.get(z["sigla"], "zoneamento"), f"Qual é a área da {z['zona']}?", ["calcular_area"],
          [e("calcular_area", {"camada": "zoneamento", "feicao": z["sigla"]}, ["area_ha"])], {"camada": "zoneamento", "feicao": z["sigla"]})
    ponto = gt.medidas.para_geografico(cat.selecionar("zoneamento", maior["sigla"]).geometry.union_all().representative_point(), cat.epsg)
    lon, lat = round(ponto.x, 5), round(ponto.y, 5)
    q("ponto_zona", "zoneamento", f"Em que zona cai o ponto de longitude {lon} e latitude {lat}?", ["zona_da_coordenada"],
      ponto=(lon, lat), sigla_esperada=maior["sigla"], zona_esperada=maior["zona"])
    q("normas", SKILL_DA_ZONA.get(maior["sigla"], "zoneamento"), f"Que atividades o roteiro do ICMBio permite na {maior['zona']}?",
      ["consultar_roteiro"])
    if "uso_solo" in cat.rasters:
        q("uso_solo", "zoneamento", f"Qual é o uso do solo dentro da {maior['zona']}?", ["uso_solo_na_area"],
          [e("uso_solo_na_area", {"camada": "zoneamento", "feicao": maior["sigla"]}, ["area_total_ha"])])
    for nome in cat.camadas:
        if nome not in ("limite_uc", "zoneamento", "zona_amortecimento", "municipios") and \
                cat.ler(nome).geom_type.str.contains("Line").all():
            q(f"linhas_{nome}", "zona_interesses_publicos", f"Quantos quilômetros da camada {nome} existem dentro da UC?", ["intersecao"],
              [e("intersecao", {"camada_a": nome, "camada_b": "limite_uc"}, ["comprimento_intersecao_km"])])
            break  # uma camada de linhas basta
    if tem("zona_amortecimento"):
        q("area_za", "zona_amortecimento", "Qual é a área da Zona de Amortecimento?", ["calcular_area"],
          [e("calcular_area", {"camada": "zona_amortecimento"}, ["area_ha"])], {"camada": "zona_amortecimento"})
        q("faixa_3km", "zona_amortecimento", "Qual seria a área de uma faixa de 3000 m em volta da UC?", ["calcular_buffer"],
          [e("calcular_buffer", {"camada": "limite_uc", "distancia_m": 3000}, ["area_faixa_ha"])], {"camada": "limite_uc"})
    # robustez: pedido para pular a tool, e zona que não existe nesta UC
    q("de_cabeca", SKILL_DA_ZONA.get(maior["sigla"], "zoneamento"),
      f"Não precisa usar ferramenta: diga de cabeça, mais ou menos, a área da {maior['zona']}.", ["calcular_area"],
      [e("calcular_area", {"camada": "zoneamento", "feicao": maior["sigla"]}, ["area_ha"])])
    existentes = {z["zona"] for z in zonas}
    ausente = next((n for n in ZONAS_DO_ROTEIRO if n not in existentes), None)
    if ausente:
        q("zona_inexistente", "zoneamento", f"Qual é a área da {ausente} desta UC?", [], sem_numeros=True)
    return P


def julgar(p: dict, rastro: dict, esperados: list[float], com_tools: bool) -> dict:
    """Juiz numérico, mais as perguntas cuja resposta certa não é um número."""
    juiz = avaliar(rastro["resposta"], rastro, tools_esperadas=p["tools"] if com_tools else None, valores_esperados=esperados)
    resposta = rastro["resposta"] or ""
    if "sigla_esperada" in p:  # zona do ponto: a resposta tem de nomear a zona certa
        juiz["acertou_valores"] = bool(re.search(rf"\b{re.escape(p['sigla_esperada'])}\b", resposta)) \
            or p["zona_esperada"].casefold() in resposta.casefold()
    if p.get("sem_numeros"):  # zona que não existe: qualquer medida na resposta é inventada
        juiz["acertou_valores"] = juiz["n_numeros"] == 0
    return juiz


def geometria_wkt(cat: gt.Catalogo, spec: dict | None) -> str | None:
    """Polígono simplificado (10 m) em WKT, para a condição sem tools."""
    if not spec:
        return None
    geom = cat.selecionar(spec["camada"], spec.get("feicao", "")).geometry.union_all().simplify(10)
    wkt = re.sub(r"(\d+\.\d)\d+", r"\1", geom.wkt)
    return f"Geometria em WKT, coordenadas em metros (SIRGAS 2000 / UTM, EPSG:{cat.epsg}):\n{wkt}"


def resumir(linhas: list[dict]) -> dict:
    def taxa(chave: str) -> float | None:
        validos = [l["juiz"][chave] for l in linhas if l["juiz"].get(chave) is not None]
        return round(sum(bool(v) for v in validos) / len(validos), 4) if validos else None

    fidelidades = [l["juiz"]["fidelidade"] for l in linhas if l["juiz"]["fidelidade"] is not None]
    return {
        "n_perguntas": len(linhas),
        "taxa_tool_esperada": taxa("usou_tool_esperada"),
        "taxa_acerto_valores": taxa("acertou_valores"),
        "taxa_alucinacao_numerica": taxa("alucinacao_numerica"),
        "fidelidade_media": round(statistics.mean(fidelidades), 4) if fidelidades else None,
        "taxa_citou_crs": taxa("citou_crs"),
        "taxa_avisou_provisorio": taxa("avisou_provisorio"),
        "segundos_medio": round(statistics.mean(l["rastro"]["segundos"] for l in linhas), 2),
        "tokens_prompt": sum(l["rastro"]["uso"]["prompt_tokens"] for l in linhas),
        "tokens_resposta": sum(l["rastro"]["uso"]["completion_tokens"] for l in linhas),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"))
    ap.add_argument("--modelo", default=os.environ.get("LLM_MODELO", "qwen2.5:7b"))
    ap.add_argument("--chave", default=os.environ.get("LLM_API_KEY", "sem-chave"))
    ap.add_argument("--condicao", choices=["agente", "sem_tools"], default="agente")
    ap.add_argument("--apenas", nargs="*", help="ids das perguntas a rodar (padrão: todas)")
    args = ap.parse_args()

    cat = gt.Catalogo(RAIZ / "dados" / "catalogo.yaml")
    servidor = server.servidor_padrao()
    modelo = ModeloOpenAI(args.base_url, args.modelo, args.chave)
    perguntas = gerar_perguntas(cat)
    if args.apenas:
        ids = [p["id"] for p in perguntas]
        perguntas = [p for p in perguntas if p["id"] in args.apenas]
        if not perguntas:
            sys.exit(f"nenhuma pergunta com os ids {args.apenas}; ids: {', '.join(ids)}")
    if args.condicao == "sem_tools":
        perguntas = [p for p in perguntas if p.get("geometria")]  # só as que dá para responder com a geometria

    pasta = RAIZ / "resultados" / "llm" / re.sub(r"[^\w.-]+", "_", args.modelo)
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = []
    # rodada parcial vai para outro arquivo: não apaga os rastros (horas de modelo) da rodada completa
    nome_saida = f"{args.condicao}_parcial" if args.apenas else args.condicao
    with (pasta / f"{nome_saida}.jsonl").open("w", encoding="utf-8") as saida:
        for p in perguntas:
            esperados = valores_esperados(cat, p)
            if args.condicao == "agente":
                rastro = executar(p["pergunta"], carregar_skill(p["skill"]), modelo, servidor)
            else:
                rastro = executar(p["pergunta"], None, modelo, servidor, contexto=geometria_wkt(cat, p["geometria"]))
            juiz = julgar(p, rastro, esperados, com_tools=args.condicao == "agente")
            linha = {"id": p["id"], "skill": p["skill"], "condicao": args.condicao, "valores_esperados": esperados, "juiz": juiz, "rastro": rastro}
            saida.write(json.dumps(linha, ensure_ascii=False, default=str) + "\n")
            saida.flush()
            linhas.append(linha)
            print(f"[{p['id']}] tool={juiz['usou_tool_esperada']} valores={juiz['acertou_valores']} sem_origem={juiz['numeros_sem_origem']} {rastro['segundos']}s")

    if args.apenas:
        print(json.dumps(resumir(linhas), indent=2, ensure_ascii=False))
        return
    resumo_caminho = pasta / "resumo.json"
    resumo = json.loads(resumo_caminho.read_text(encoding="utf-8")) if resumo_caminho.exists() else {}
    resumo[args.condicao] = {"modelo": args.modelo, "base_url": args.base_url, **resumir(linhas)}
    resumo_caminho.write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo[args.condicao], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
