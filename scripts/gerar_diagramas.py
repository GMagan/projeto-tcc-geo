#!/usr/bin/env python3
"""Desenha os diagramas do projeto: SADT/IDEF0 (A-0 e A0) e arquitetura.

Saída em resultados/diagramas/ (PDF vetorial). Uso: python scripts/gerar_diagramas.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

FIG = Path(__file__).resolve().parents[1] / "resultados" / "diagramas"
TINTA, SUAVE, FUNDO, DESTAQUE = "#1f1f1f", "#5f5f5f", "#eef3f8", "#d9e6f2"


def caixa(ax, x, y, w, h, texto, cor=FUNDO, tamanho=9, negrito=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=cor, ec=TINTA, lw=1.0))
    ax.text(x + w / 2, y + h / 2, texto, ha="center", va="center", fontsize=tamanho, color=TINTA,
            fontweight="bold" if negrito else "normal", linespacing=1.35)


def seta(ax, origem, destino, texto="", lado="acima", tamanho=7.5, curva=0.0):
    ax.annotate("", xy=destino, xytext=origem, arrowprops={"arrowstyle": "-|>", "color": TINTA, "lw": 1.0,
                                                           "connectionstyle": f"arc3,rad={curva}", "shrinkA": 0, "shrinkB": 0})
    if texto:
        mx, my = (origem[0] + destino[0]) / 2, (origem[1] + destino[1]) / 2
        desloc = {"acima": (0, 0.12, "center", "bottom"), "abaixo": (0, -0.12, "center", "top"),
                  "direita": (0.1, 0, "left", "center"), "esquerda": (-0.1, 0, "right", "center")}[lado]
        ax.text(mx + desloc[0], my + desloc[1], texto, ha=desloc[2], va=desloc[3], fontsize=tamanho, color=SUAVE, linespacing=1.3)


def tela(largura, altura, xmax, ymax):
    fig, ax = plt.subplots(figsize=(largura, altura))
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    return fig, ax


def salvar(fig, nome):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / nome, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print("figura:", nome)


def sadt_contexto():
    fig, ax = tela(8.4, 4.7, 20, 10)
    caixa(ax, 5.6, 3.9, 7.2, 2.2, "A0\nProduzir tópico do plano de manejo\ncom números rastreáveis", DESTAQUE, 8.5, True)
    # entradas (esquerda)
    for y, texto in ((5.5, "Pergunta em linguagem natural"), (4.5, "Coordenadas e camadas\n(shapefile, GeoPackage, raster)")):
        seta(ax, (0.3, y), (5.6, y), texto, "acima", 7.3)
    # controles (cima)
    for x, texto in ((6.2, "Persona"), (7.9, "Skill\n(Markdown)"), (10.3, "Roteiro do\nICMBio (RAG)"), (12.3, "Modelo\nde IA")):
        seta(ax, (x, 7.9), (x, 6.1))
        ax.text(x, 8.0, texto, ha="center", va="bottom", fontsize=7.5, color=SUAVE, linespacing=1.3)
    # saídas (direita)
    for y, texto in ((5.85, "Resposta com a origem\nde cada número"), (5.0, "Dados espaciais\n(ha, km, JSON, mapa)"), (4.15, "Rastro auditável\nda execução")):
        seta(ax, (12.8, y), (14.6, y))
        ax.text(14.8, y, texto, ha="left", va="center", fontsize=7.5, color=SUAVE, linespacing=1.25)
    # mecanismos (baixo)
    for x, texto in ((6.8, "Agente\n(orquestrador)"), (9.2, "Tools do\nservidor MCP"), (11.6, "GeoPandas,\nShapely, PROJ")):
        seta(ax, (x, 2.1), (x, 3.9))
        ax.text(x, 2.0, texto, ha="center", va="top", fontsize=7.5, color=SUAVE, linespacing=1.3)
    ax.text(0.3, 6.6, "ENTRADAS", ha="left", va="center", fontsize=8, color=TINTA, fontweight="bold")
    ax.text(9.2, 9.6, "CONTROLES", ha="center", va="center", fontsize=8, color=TINTA, fontweight="bold")
    ax.text(14.8, 6.6, "SAÍDAS", ha="left", va="center", fontsize=8, color=TINTA, fontweight="bold")
    ax.text(9.2, 0.4, "MECANISMOS", ha="center", va="center", fontsize=8, color=TINTA, fontweight="bold")
    salvar(fig, "sadt_contexto.pdf")


def sadt_decomposicao():
    fig, ax = tela(8.4, 3.5, 24, 8.6)
    fases = [
        (1.8, "A1\nInterpretar a pergunta\ne escolher a tool", "Persona, skill,\nroteiro (RAG), modelo", "Agente\n(modelo de linguagem)"),
        (9.4, "A2\nCalcular\n(determinístico)", "Geometria analítica,\nCRS de trabalho, catálogo", "Tool MCP\n(GeoPandas, PROJ)"),
        (17.0, "A3\nRedigir a resposta\ncitando a origem", "Persona e skill\n(copiar, não recalcular)", "Agente e registro\nde auditoria"),
    ]
    y = 3.3
    for x, titulo, controle, mecanismo in fases:
        caixa(ax, x, y, 5.0, 2.0, titulo, DESTAQUE, 7.0, True)
        seta(ax, (x + 2.5, y + 3.2), (x + 2.5, y + 2.0))
        ax.text(x + 2.5, y + 3.3, controle, ha="center", va="bottom", fontsize=7.3, color=SUAVE, linespacing=1.3)
        seta(ax, (x + 2.5, y - 1.2), (x + 2.5, y))
        ax.text(x + 2.5, y - 1.3, mecanismo, ha="center", va="top", fontsize=7.3, color=SUAVE, linespacing=1.3)
    meio = y + 1.0
    seta(ax, (0.1, meio), (1.8, meio))
    ax.text(0.9, meio + 0.15, "pergunta", ha="center", va="bottom", fontsize=6.6, color=SUAVE)
    seta(ax, (6.8, meio), (9.4, meio))
    ax.text(8.1, meio + 0.15, "chamada\nestruturada\n(tool, JSON)", ha="center", va="bottom", fontsize=6.4, color=SUAVE, linespacing=1.25)
    seta(ax, (14.4, meio), (17.0, meio))
    ax.text(15.7, meio + 0.15, "resultado\nexato (valor,\nunidade, CRS)", ha="center", va="bottom", fontsize=6.4, color=SUAVE, linespacing=1.25)
    seta(ax, (22.0, meio), (23.8, meio))
    ax.text(22.9, meio + 0.15, "resposta", ha="center", va="bottom", fontsize=6.6, color=SUAVE)
    salvar(fig, "sadt_decomposicao.pdf")


def arquitetura():
    fig, ax = tela(8.4, 5.6, 17, 11.4)
    caixa(ax, 5.3, 9.4, 6.4, 1.5, "Servidor de inferência (Ollama)\nmodelo de linguagem: interpreta e redige", FUNDO, 8)
    caixa(ax, 5.3, 6.4, 6.4, 1.8, "Orquestrador\nOpen WebUI (uso interativo) ou\npacote agente/ (avaliação automática)", DESTAQUE, 8, True)
    caixa(ax, 0.3, 6.6, 3.9, 1.4, "Skills e persona\n(Markdown no Git)", FUNDO, 8)
    caixa(ax, 12.8, 6.6, 3.9, 1.4, "Rastros da execução\n(JSONL; Langfuse\nopcional)", FUNDO, 7.6)
    caixa(ax, 5.3, 3.2, 6.4, 1.9, "Servidor MCP (TCC-GeoWorker)\n17 tools determinísticas\ngeotools: GeoPandas, Shapely, PROJ", DESTAQUE, 8, True)
    caixa(ax, 0.3, 3.45, 3.9, 1.4, "Catálogo de camadas\n(GeoPackage e raster)", FUNDO, 8)
    caixa(ax, 12.8, 3.45, 3.9, 1.4, "Roteiro do ICMBio\n(índice BM25)", FUNDO, 8)
    caixa(ax, 2.6, 0.3, 11.8, 1.5, "Avaliação: pytest (geometria analítica e gabarito do plano),\njuiz numérico determinístico e DeepEval", FUNDO, 8)
    seta(ax, (7.6, 8.2), (7.6, 9.4))
    ax.text(7.45, 8.8, "mensagens e tools", ha="right", va="center", fontsize=7, color=SUAVE)
    seta(ax, (9.4, 9.4), (9.4, 8.2))
    ax.text(9.55, 8.8, "resposta ou pedido de tool", ha="left", va="center", fontsize=7, color=SUAVE)
    seta(ax, (7.6, 6.4), (7.6, 5.1))
    ax.text(7.45, 5.75, "MCP: tools/call", ha="right", va="center", fontsize=7, color=SUAVE)
    seta(ax, (9.4, 5.1), (9.4, 6.4))
    ax.text(9.55, 5.75, "resultado em JSON", ha="left", va="center", fontsize=7, color=SUAVE)
    seta(ax, (4.2, 7.3), (5.3, 7.3))
    seta(ax, (11.7, 7.3), (12.8, 7.3))
    seta(ax, (4.2, 4.15), (5.3, 4.15))
    seta(ax, (12.8, 4.15), (11.7, 4.15))
    seta(ax, (8.5, 1.8), (8.5, 3.2))
    ax.text(8.65, 2.5, "testa", ha="left", va="center", fontsize=7, color=SUAVE)
    salvar(fig, "arquitetura.pdf")


if __name__ == "__main__":
    sadt_contexto()
    sadt_decomposicao()
    arquitetura()
