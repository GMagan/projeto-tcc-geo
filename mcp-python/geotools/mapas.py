"""Tópico 6.1 do plano: mapa de zoneamento (PNG e PDF) com legenda, grade UTM e escala."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sem tela: roda em servidor e em contêiner
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

from .catalogo import Catalogo
from .erros import ErroGeo
from .medidas import ha

# Matizes da legenda do plano (verde, rosa, vermelho, amarelo), com luminosidade
# ajustada para separar bem também em daltonismo (conferido com o validador de paleta).
CORES_ZONAS = {  # verdes = pouca intervenção, amarelos/laranjas = muita, demais = usos diferenciados
    "ZP": "#145a32", "ZC": "#2e8f2a", "ZUR": "#7dbb5b", "ZUM": "#b5c94c", "ZUC": "#8c7a3a", "ZMF": "#5e8c6a",
    "ZI": "#c79a00", "ZPO": "#e07b39", "ZPR": "#d9a066", "ZUI": "#8a8a8a",
    "ZST": "#5b6bbf", "ZDIP": "#d9261c", "ZAA": "#cf6fc8", "ZUD": "#7b3fa0",
}
COR_PADRAO = "#7a7a7a"
COR_POR_NOME = ((("hidro", "rio", "agua", "drenag", "massa", "lago", "reservat"), "#5b9bd5"),
                (("estrad", "rodov", "via", "acesso", "trilha"), "#8a5a2b"))
TINTA, TINTA_SUAVE = "#1f1f1f", "#6b6b6b"
TEMAS = ("zoneamento", "zona_amortecimento")


def _milhar(valor: float, _pos=None) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def _barra_de_escala(ax, comprimento_m: float) -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x, y = x0 + 0.05 * (x1 - x0), y0 + 0.045 * (y1 - y0)
    ax.plot([x, x + comprimento_m], [y, y], color=TINTA, lw=3, solid_capstyle="butt", zorder=9)
    ax.plot([x, x + comprimento_m / 2], [y, y], color="white", lw=1.4, solid_capstyle="butt", zorder=10)
    rotulo = f"{comprimento_m / 1000:g} km" if comprimento_m >= 1000 else f"{comprimento_m:g} m"
    ax.text(x + comprimento_m / 2, y + 0.012 * (y1 - y0), rotulo, ha="center", va="bottom", fontsize=8, color=TINTA, zorder=10)


def _norte(ax) -> None:
    ax.annotate(
        "N", xy=(0.95, 0.95), xytext=(0.95, 0.865), xycoords="axes fraction", ha="center", va="center",
        fontsize=10, color=TINTA, arrowprops={"arrowstyle": "-|>", "color": TINTA, "lw": 1.2}, zorder=10,
    )


def gerar_mapa(cat: Catalogo, tema: str = "zoneamento", pasta_saida: str | Path | None = None) -> dict:
    """Desenha o mapa do tema pedido e grava PNG (200 dpi) e PDF vetorial."""
    if tema not in TEMAS:
        raise ErroGeo(f"tema '{tema}' não disponível; temas: {', '.join(TEMAS)}")
    pasta = Path(pasta_saida or os.environ.get("GEO_SAIDAS") or cat.pasta.parent / "resultados" / "mapas")
    pasta.mkdir(parents=True, exist_ok=True)

    limite = cat.ler("limite_uc")
    zonas = cat.ler("zoneamento")
    meta = cat.meta("zoneamento")
    campo_sigla, campo_nome = meta.get("campo_sigla", "sigla"), meta.get("campo_nome", "zona")
    tem = lambda camada: camada in cat.camadas  # noqa: E731
    za = cat.ler("zona_amortecimento") if tem("zona_amortecimento") else None

    foco = za if (tema == "zona_amortecimento" and za is not None) else limite
    xmin, ymin, xmax, ymax = foco.total_bounds
    lado = max(xmax - xmin, ymax - ymin) * 1.16
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

    fig, ax = plt.subplots(figsize=(8, 8.6), dpi=200)
    ax.set_facecolor("#f4f2ec")

    # demais camadas fornecidas pelo usuário, com cor pelo nome do arquivo
    extras = []
    for nome in cat.camadas:
        if nome in ("limite_uc", "zoneamento", "zona_amortecimento", "municipios"):
            continue
        cor = next((c for chaves, c in COR_POR_NOME if any(k in nome for k in chaves)), COR_PADRAO)
        camada = cat.ler(nome)
        if (camada.geom_type.str.contains("Polygon")).all():
            camada.plot(ax=ax, color=cor, alpha=0.3, edgecolor="none", zorder=1)
            extras.append(Patch(facecolor=cor, alpha=0.3, label=nome.replace("_", " ").capitalize()))
        else:
            camada.plot(ax=ax, color=cor, lw=0.8, markersize=12, zorder=6)
            extras.append(Line2D([0], [0], color=cor, lw=0.8, label=nome.replace("_", " ").capitalize()))
    if tem("municipios"):
        municipios = cat.ler("municipios")
        municipios.boundary.plot(ax=ax, color=TINTA_SUAVE, linewidth=0.7, linestyle="--", zorder=2)
    if za is not None:
        za.plot(ax=ax, facecolor="#f6c56f" if tema == "zona_amortecimento" else "none", alpha=0.35, edgecolor="none", zorder=3)
        za.boundary.plot(ax=ax, color="#d98200", lw=1.4, zorder=4)

    desenhadas, legenda = [], []
    for sigla, grupo in zonas.groupby(campo_sigla, sort=False):
        cor = CORES_ZONAS.get(str(sigla), COR_PADRAO)
        grupo.plot(ax=ax, facecolor=cor, edgecolor=TINTA, lw=0.35, zorder=5)
        desenhadas.append(str(sigla))
        area = ha(grupo.geometry.union_all().area)
        nome = str(grupo[campo_nome].iloc[0])
        legenda.append(Patch(facecolor=cor, edgecolor=TINTA, lw=0.5, label=f"{nome} ({sigla}): {_milhar_ha(area)} ha"))
    limite.boundary.plot(ax=ax, color=TINTA, lw=1.5, zorder=7)
    legenda.append(Line2D([0], [0], color=TINTA, lw=1.5, label=f"Limite da UC: {_milhar_ha(ha(limite.geometry.union_all().area))} ha"))
    if za is not None:
        legenda.append(Line2D([0], [0], color="#d98200", lw=1.4, label=f"Zona de Amortecimento: {_milhar_ha(ha(za.geometry.union_all().area))} ha"))
    legenda += extras
    if tem("municipios"):
        legenda.append(Line2D([0], [0], color=TINTA_SUAVE, lw=0.7, ls="--", label="Limite municipal"))

    ax.set_xlim(cx - lado / 2, cx + lado / 2)
    ax.set_ylim(cy - lado / 2, cy + lado / 2)
    ax.set_aspect("equal")

    if tem("municipios"):
        from shapely.geometry import box

        janela = box(*ax.get_xlim()[:1], *ax.get_ylim()[:1], ax.get_xlim()[1], ax.get_ylim()[1])
        for _, mun in municipios.iterrows():
            visivel = mun.geometry.intersection(janela).difference(limite.geometry.union_all().buffer(lado * 0.02))
            if not visivel.is_empty and visivel.area > 0.02 * janela.area:
                p = visivel.representative_point()
                ax.text(p.x, p.y, mun[cat.meta("municipios").get("campo_nome", "nome")], fontsize=9, color=TINTA_SUAVE,
                        ha="center", va="center", style="italic", zorder=8)

    ax.set_xlabel("E (m)", fontsize=8, color=TINTA_SUAVE)
    ax.set_ylabel("N (m)", fontsize=8, color=TINTA_SUAVE)
    ax.xaxis.set_major_formatter(FuncFormatter(_milhar))
    ax.yaxis.set_major_formatter(FuncFormatter(_milhar))
    ax.xaxis.set_major_locator(plt.MaxNLocator(4))
    ax.yaxis.set_major_locator(plt.MaxNLocator(4))
    ax.tick_params(labelsize=7, colors=TINTA_SUAVE, length=3)
    plt.setp(ax.get_yticklabels(), rotation=90, va="center")
    ax.grid(color="white", lw=0.6, zorder=0)
    for borda in ax.spines.values():
        borda.set_color(TINTA_SUAVE)
        borda.set_linewidth(0.6)

    passo = next(p for p in (5000, 2000, 1000, 500, 200, 100, 50) if p <= lado / 4)
    _barra_de_escala(ax, passo)
    _norte(ax)

    titulo = "Zoneamento" if tema == "zoneamento" else "Zona de Amortecimento"
    ax.set_title(f"{titulo}: {cat.uc.get('nome', 'UC')}", fontsize=12, color=TINTA, loc="left", pad=10)
    ax.legend(handles=legenda, loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=2, fontsize=8, frameon=False,
              labelcolor=TINTA, handlelength=1.6, columnspacing=1.6)
    procedencia = cat.procedencia("limite_uc", "zoneamento")
    rodape = f"SIRGAS 2000 / UTM (EPSG:{cat.epsg}). Fonte do zoneamento: {meta.get('fonte', '')}"
    if procedencia["provisorio"]:
        rodape += " DADO PROVISÓRIO."
    fig.text(0.5, 0.012, rodape, ha="center", va="bottom", fontsize=6.5, color=TINTA_SUAVE, wrap=True)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.95, bottom=0.2)

    png, pdf = pasta / f"mapa_{tema}.png", pasta / f"mapa_{tema}.pdf"
    fig.savefig(png, dpi=200)
    fig.savefig(pdf)
    plt.close(fig)
    return {
        "status": "sucesso",
        "ferramenta": "gerar_mapa",
        "tema": tema,
        "pasta": str(pasta),
        "arquivo_png": png.name,
        "arquivo_pdf": pdf.name,
        "sha256_png": hashlib.sha256(png.read_bytes()).hexdigest(),
        "zonas_desenhadas": desenhadas,
        "extensao_utm": [round(float(v), 1) for v in (*ax.get_xlim(), *ax.get_ylim())],
        "crs": cat.crs,
        **procedencia,
    }


def _milhar_ha(valor: float) -> str:
    """616.66 -> '616,66' (padrão brasileiro)."""
    return f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
