#!/usr/bin/env python3
# Registro histórico: precisa de scipy, scikit-image e pillow, que o projeto não instala.
"""Vetoriza o zoneamento do PESC a partir das figuras do plano de manejo.

DADO PROVISÓRIO. O shapefile oficial do zoneamento (IAT/STCP) não é público.
Este script reconstrói uma aproximação a partir das Figuras 3 a 8 do Plano de
Manejo do Parque Estadual de Santa Clara (IAT, 2026), que trazem a grade UTM
impressa (SIRGAS 2000 / UTM 22S):

  1. extrai as figuras do PDF;
  2. georreferencia cada figura pelas marcas da grade (ajuste linear por eixo);
  3. classifica pixels por cor (limite e zonas) no espaço HSV;
  4. reamostra para uma grade UTM comum, preenche oclusões de rótulos pelo
     vizinho conhecido mais próximo e poligoniza.

Cada zona sai da figura dedicada a ela (Fig. 5 ZAA, Fig. 6 ZI, Fig. 7 ZDIP); a
Zona de Conservação é o complemento dentro do limite. O limite é a linha
média do contorno verde-limão das Figuras 3 a 7.

Saídas (em --saida):
  zoneamento_vetorizado.gpkg  camadas limite_uc, zoneamento, zona_amortecimento
  relatorio_vetorizacao.json  resíduos, tamanho de pixel, áreas e incertezas
  conferencia_*.png           sobreposições para inspeção visual

Uso:
  python scripts/vetorizar_zoneamento.py --pdf ../anexo_1_planodemanejopesantaclara_rev03.pdf
"""
from __future__ import annotations

import argparse
import io
import json
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pymupdf
import rasterio.features
from affine import Affine
from PIL import Image
from scipy import ndimage
from shapely.geometry import shape
from shapely.ops import unary_union
from skimage.color import rgb2hsv
from skimage.morphology import disk, skeletonize

EPSG_TRABALHO = 31982  # SIRGAS 2000 / UTM 22S

GRADE_PARQUE = {"e": [400_000, 402_000, 404_000], "n": [7_164_000, 7_162_000, 7_160_000]}
FIGURAS = {
    "fig3_zonas": {"pagina": 29, **GRADE_PARQUE},
    "fig4_zc": {"pagina": 30, **GRADE_PARQUE},
    "fig5_zaa": {"pagina": 32, **GRADE_PARQUE},
    "fig6_zi": {"pagina": 34, **GRADE_PARQUE},
    "fig7_zdip": {"pagina": 35, **GRADE_PARQUE},
    "fig8_za": {
        "pagina": 37,
        "e": [399_000, 402_500, 406_000],
        "n": [7_168_000, 7_164_500, 7_161_000, 7_157_500],
    },
}
FIGS_LIMITE = ["fig3_zonas", "fig4_zc", "fig5_zaa", "fig6_zi", "fig7_zdip"]

ZONAS = {
    "ZC": "Zona de Conservação",
    "ZAA": "Zona de Adequação Ambiental",
    "ZI": "Zona de Infraestrutura",
    "ZDIP": "Zona de Diferentes Interesses Públicos",
}
FONTE = (
    "Vetorizado das Figuras 3 a 8 do Plano de Manejo do Parque Estadual de "
    "Santa Clara (IAT, 2026) por scripts/vetorizar_zoneamento.py"
)


OITO_VIZINHOS = np.ones((3, 3), dtype=bool)


def fechar(mascara: np.ndarray, raio: int) -> np.ndarray:
    """Fechamento morfológico com disco (preenche falhas de até 2*raio pixels)."""
    borda = raio + 1
    m = np.pad(mascara, borda)
    return ndimage.binary_closing(m, structure=disk(raio))[borda:-borda, borda:-borda]


def dilatar(mascara: np.ndarray, raio: int) -> np.ndarray:
    return ndimage.binary_dilation(mascara, structure=disk(raio))


def remover_pequenos(mascara: np.ndarray, celulas_min: float) -> np.ndarray:
    """Descarta componentes conexos (8 vizinhos) menores que `celulas_min`."""
    rotulos, n = ndimage.label(mascara, structure=OITO_VIZINHOS)
    if n == 0:
        return mascara
    tamanhos = ndimage.sum(mascara, rotulos, index=np.arange(1, n + 1))
    return np.isin(rotulos, 1 + np.where(tamanhos >= celulas_min)[0])


# --------------------------------------------------------------------------
# 1. extração das figuras
# --------------------------------------------------------------------------
def extrair_figura(doc: pymupdf.Document, pagina: int) -> np.ndarray:
    """Devolve a maior imagem embutida na página (RGB)."""
    imagens = doc[pagina - 1].get_images(full=True)
    xref = max(imagens, key=lambda im: im[2] * im[3])[0]
    dados = doc.extract_image(xref)["image"]
    return np.asarray(Image.open(io.BytesIO(dados)).convert("RGB"))


# --------------------------------------------------------------------------
# 2. georreferenciamento pelas marcas de grade
# --------------------------------------------------------------------------
@dataclass
class Georref:
    """E = e0 + de * coluna ; N = n0 + dn * linha (índice do pixel = centro)."""

    e0: float
    de: float
    n0: float
    dn: float
    esq: int
    dir: int
    topo: int
    base: int
    residuo_max_m: float

    @property
    def pixel_m(self) -> float:
        return (abs(self.de) + abs(self.dn)) / 2

    def coluna(self, e: np.ndarray) -> np.ndarray:
        return (e - self.e0) / self.de

    def linha(self, n: np.ndarray) -> np.ndarray:
        return (n - self.n0) / self.dn


def _centros_de_marcas(perfil: np.ndarray, ini: int, fim: int) -> list[float]:
    """Centros das sequências de pixels escuros com 2 a 6 px de largura."""
    idx = np.where(perfil)[0]
    idx = idx[(idx > ini) & (idx < fim)]
    centros, inicio, anterior = [], None, None
    for i in idx:
        if inicio is None:
            inicio = anterior = i
        elif i == anterior + 1:
            anterior = i
        else:
            if 2 <= anterior - inicio + 1 <= 6:
                centros.append((inicio + anterior) / 2)
            inicio = anterior = i
    if inicio is not None and 2 <= anterior - inicio + 1 <= 6:
        centros.append((inicio + anterior) / 2)
    return centros


def georreferenciar(rgb: np.ndarray, ticks_e: list[int], ticks_n: list[int]) -> Georref:
    alt, larg, _ = rgb.shape
    escuro = rgb.astype(int).sum(axis=2) < 150
    linhas = np.where(escuro.sum(axis=1) > 0.6 * larg)[0]
    colunas = np.where(escuro.sum(axis=0) > 0.6 * alt)[0]
    topo, base, esq, dir_ = linhas.min(), linhas.max(), colunas.min(), colunas.max()

    cima = _centros_de_marcas(escuro[topo - 8 : topo - 2, :].sum(axis=0) >= 3, esq, dir_)
    baixo = _centros_de_marcas(escuro[base + 3 : base + 9, :].sum(axis=0) >= 3, esq, dir_)
    esquerda = _centros_de_marcas(escuro[:, esq - 8 : esq - 2].sum(axis=1) >= 3, topo, base)
    direita = _centros_de_marcas(escuro[:, dir_ + 3 : dir_ + 9].sum(axis=1) >= 3, topo, base)
    if not (len(cima) == len(baixo) == len(ticks_e) and len(esquerda) == len(direita) == len(ticks_n)):
        raise RuntimeError(
            f"marcas de grade não conferem: cima={cima} baixo={baixo} esq={esquerda} dir={direita}"
        )
    xs = (np.array(cima) + np.array(baixo)) / 2
    ys = (np.array(esquerda) + np.array(direita)) / 2
    de, e0 = np.polyfit(xs, ticks_e, 1)
    dn, n0 = np.polyfit(ys, ticks_n, 1)
    residuo = max(
        np.abs(e0 + de * xs - ticks_e).max(),
        np.abs(n0 + dn * ys - ticks_n).max(),
    )
    return Georref(e0, de, n0, dn, int(esq), int(dir_), int(topo), int(base), float(residuo))


# --------------------------------------------------------------------------
# 3. classificação por cor
# --------------------------------------------------------------------------
def mascaras_de_cor(rgb: np.ndarray) -> dict[str, np.ndarray]:
    hsv = rgb2hsv(rgb)
    h, s, v = hsv[..., 0] * 360, hsv[..., 1], hsv[..., 2]
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    branco = (v > 0.90) & (s < 0.10)  # texto e linhas de chamada dos rótulos
    simbolo = (h > 150) & (h < 225) & (s > 0.55) & (v > 0.65)  # cachoeiras, barragens (ciano/azul)
    return {
        "limite": (h > 85) & (h < 125) & (s > 0.60) & (v > 0.80),
        "rosa": ((h > 300) | (h < 5)) & (s > 0.12) & (s < 0.45) & (v > 0.50) & (r - g > 25) & (b - g > 8),
        "amarelo": (h > 40) & (h < 68) & (s > 0.45) & (v > 0.60) & (r > 150) & (g > 140),
        "vermelho": ((h > 345) | (h < 22)) & (s > 0.60) & (v > 0.60),
        "laranja": (h > 22) & (h < 50) & (s > 0.55) & (v > 0.72),
        "verde_zc": (h > 95) & (h < 125) & (s > 0.50) & (v > 0.30) & (v < 0.55),
        "rotulo": dilatar(branco | simbolo, 4),  # +4 px cobre o contorno preto e a suavização
    }


def preencher_oclusoes(positivo: np.ndarray, desconhecido: np.ndarray) -> np.ndarray:
    """Pixels encobertos por rótulos recebem a classe do pixel conhecido mais próximo."""
    conhecido = positivo | ~desconhecido
    idx = ndimage.distance_transform_edt(~conhecido, return_distances=False, return_indices=True)
    return positivo[tuple(idx)]


# --------------------------------------------------------------------------
# 4. grade UTM comum
# --------------------------------------------------------------------------
@dataclass
class Grade:
    e_min: float
    n_max: float
    res: float
    nx: int
    ny: int

    @classmethod
    def da_figura(cls, geo: Georref, res: float) -> "Grade":
        e_min, e_max = geo.e0 + geo.de * (geo.esq + 1), geo.e0 + geo.de * (geo.dir - 1)
        n_max, n_min = geo.n0 + geo.dn * (geo.topo + 1), geo.n0 + geo.dn * (geo.base - 1)
        return cls(e_min, n_max, res, int((e_max - e_min) // res), int((n_max - n_min) // res))

    @property
    def transform(self) -> Affine:
        return Affine(self.res, 0, self.e_min, 0, -self.res, self.n_max)

    def reamostrar(self, mascara: np.ndarray, geo: Georref) -> np.ndarray:
        """Vizinho mais próximo: cada célula da grade lê o pixel da figura que a contém."""
        e = self.e_min + (np.arange(self.nx) + 0.5) * self.res
        n = self.n_max - (np.arange(self.ny) + 0.5) * self.res
        col = np.rint(geo.coluna(e)).astype(int)
        lin = np.rint(geo.linha(n)).astype(int)
        ok_c = (col > geo.esq) & (col < geo.dir)
        ok_l = (lin > geo.topo) & (lin < geo.base)
        saida = np.zeros((self.ny, self.nx), dtype=bool)
        saida[np.ix_(ok_l, ok_c)] = mascara[np.ix_(lin[ok_l], col[ok_c])]
        return saida

    def poligonizar(self, mascara: np.ndarray, tolerancia_m: float, area_min_m2: float = 0.0):
        mascara = remover_pequenos(mascara, area_min_m2 / self.res**2)
        formas = rasterio.features.shapes(
            mascara.astype(np.uint8), mask=mascara, connectivity=8, transform=self.transform
        )
        poligonos = [shape(geom) for geom, _ in formas]
        if not poligonos:
            raise RuntimeError("máscara vazia: nenhuma feição encontrada")
        return unary_union(poligonos).simplify(tolerancia_m, preserve_topology=True).buffer(0)


def _pontas_e_geodesicas(linha: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pontas do esqueleto da linha e a distância (em células) entre elas *ao longo* da linha."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra

    esq = skeletonize(linha)
    vizinhos = ndimage.convolve(esq.astype(int), np.ones((3, 3), int), mode="constant") - 1
    pontas = np.argwhere(esq & (vizinhos == 1))
    alt, larg = esq.shape
    ys, xs = np.nonzero(esq)
    indice = -np.ones(esq.shape, dtype=int)
    indice[ys, xs] = np.arange(len(ys))
    origem, destino, peso = [], [], []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        y2, x2 = ys + dy, xs + dx
        ok = (y2 >= 0) & (y2 < alt) & (x2 >= 0) & (x2 < larg)
        viz = indice[y2[ok], x2[ok]]
        tem = viz >= 0
        origem.append(np.arange(len(ys))[ok][tem])
        destino.append(viz[tem])
        peso.append(np.full(int(tem.sum()), np.hypot(dy, dx)))
    n = len(ys)
    grafo = coo_matrix((np.concatenate(peso), (np.concatenate(origem), np.concatenate(destino))), shape=(n, n))
    fontes = indice[pontas[:, 0], pontas[:, 1]]
    geodesica = dijkstra(grafo, directed=False, indices=fontes)[:, fontes]
    return pontas, geodesica


def _maior_componente(mascara: np.ndarray) -> np.ndarray:
    rotulos, n = ndimage.label(mascara)
    if n == 0:
        return mascara
    tamanhos = ndimage.sum(mascara, rotulos, index=np.arange(1, n + 1))
    return rotulos == (1 + int(np.argmax(tamanhos)))


def interior_pela_linha_media(
    linha: np.ndarray, res: float, fechamento_m: float, ponte_max_m: float
) -> tuple[np.ndarray, float, list[float]]:
    """Região delimitada pela linha média de um contorno desenhado com espessura.

    Rótulos e símbolos desenhados sobre o contorno o interrompem. Enquanto o
    contorno não fecha, liga-se o par de pontas soltas mais próximo (até
    `ponte_max_m`) cujo caminho *ao longo da linha* seja bem maior que a
    distância em linha reta -- isto é, pontas de lados opostos de uma falha, e
    não as duas pontas de um mesmo ramo curto. Depois preenche o interior,
    mede a espessura do traço e desconta meia espessura da borda externa.

    Devolve (interior, espessura do traço em m, comprimento das pontes em m).
    """
    from skimage.draw import line as tracar

    linha = fechar(linha, max(1, round(fechamento_m / res)))
    linha = remover_pequenos(linha, 12)  # ruído
    meia_cel = np.median(ndimage.distance_transform_edt(linha)[skeletonize(linha)])
    pontes: list[float] = []
    for _ in range(20):
        cheio = _maior_componente(ndimage.binary_fill_holes(linha))
        if cheio.sum() - (linha & cheio).sum() > 5 * linha.sum():
            break  # contorno fechado: o interior é bem maior que o traço
        pontas, geodesica = _pontas_e_geodesicas(linha)
        melhor = None
        for i in range(len(pontas)):
            for j in range(i + 1, len(pontas)):
                reta = float(np.hypot(*(pontas[i] - pontas[j])))
                if reta * res <= ponte_max_m and geodesica[i, j] >= 4 * reta:
                    if melhor is None or reta < melhor[0]:
                        melhor = (reta, i, j)
        if melhor is None:
            raise RuntimeError("contorno não fecha: aumente ponte_max_m ou revise as cores")
        reta, i, j = melhor
        rr, cc = tracar(*pontas[i], *pontas[j])
        segmento = np.zeros_like(linha)
        segmento[rr, cc] = True
        linha = linha | dilatar(segmento, max(1, int(round(meia_cel))))
        pontes.append(round(reta * res, 1))
    else:
        raise RuntimeError("contorno não fecha após 20 pontes")
    linha = linha & cheio
    meia_espessura = meia_cel * res
    interior = ndimage.distance_transform_edt(cheio) * res > meia_espessura
    return interior, float(2 * meia_espessura), pontes


# --------------------------------------------------------------------------
# pipeline
# --------------------------------------------------------------------------
def vetorizar(pdf: Path, saida: Path, res_parque: float = 2.0, res_za: float = 4.0) -> dict:
    saida.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    figs, geos, cores = {}, {}, {}
    for nome, cfg in FIGURAS.items():
        figs[nome] = extrair_figura(doc, cfg["pagina"])
        geos[nome] = georreferenciar(figs[nome], cfg["e"], cfg["n"])
        cores[nome] = mascaras_de_cor(figs[nome])

    relatorio: dict = {
        "fonte": FONTE,
        "crs": f"EPSG:{EPSG_TRABALHO}",
        "figuras": {
            nome: {
                "pagina_pdf": FIGURAS[nome]["pagina"],
                "pixel_m": round(g.pixel_m, 3),
                "residuo_max_grade_m": round(g.residuo_max_m, 2),
            }
            for nome, g in geos.items()
        },
    }

    # ---- limite da UC: linha média do contorno verde-limão (Figuras 3 a 7)
    grade = Grade.da_figura(geos["fig3_zonas"], res_parque)
    px = max(geos[f].pixel_m for f in FIGS_LIMITE)
    linha = np.zeros((grade.ny, grade.nx), dtype=bool)
    areas_individuais = {}
    for f in FIGS_LIMITE:
        linha_f = grade.reamostrar(cores[f]["limite"], geos[f])
        linha |= linha_f
        try:  # cada figura sozinha: estimativa independente, para medir a dispersão
            interior_f, _, _ = interior_pela_linha_media(linha_f, grade.res, px, ponte_max_m=400)
            areas_individuais[f] = round(float(interior_f.sum()) * grade.res**2 / 1e4, 2)
        except RuntimeError:
            areas_individuais[f] = None
    parque, espessura, pontes = interior_pela_linha_media(linha, grade.res, px, ponte_max_m=150)
    limite = grade.poligonizar(parque, tolerancia_m=px / 2)

    # ---- zonas: cada uma da figura dedicada, com oclusões preenchidas
    def zona(fig: str, cor: str, raio_fechamento: int) -> np.ndarray:
        positivo = cores[fig][cor]
        if raio_fechamento:
            positivo = fechar(positivo, raio_fechamento)
        return grade.reamostrar(preencher_oclusoes(positivo, cores[fig]["rotulo"]), geos[fig]) & parque

    m_zdip = zona("fig7_zdip", "vermelho", 0)
    m_zi = zona("fig6_zi", "amarelo", 1) & ~m_zdip
    m_zaa = zona("fig5_zaa", "rosa", 1) & ~m_zdip & ~m_zi
    m_zaa_fig3 = zona("fig3_zonas", "rosa", 1) & ~m_zdip & ~m_zi  # conferência

    area_min = 4 * px**2
    p_zdip = grade.poligonizar(m_zdip, px / 2, area_min).intersection(limite)
    p_zi = grade.poligonizar(m_zi, px / 2, area_min).intersection(limite).difference(p_zdip)
    p_zaa = grade.poligonizar(m_zaa, px / 2, area_min).intersection(limite).difference(p_zdip.union(p_zi))
    p_zc = limite.difference(unary_union([p_zdip, p_zi, p_zaa]))
    poligonos = {"ZC": p_zc, "ZAA": p_zaa, "ZI": p_zi, "ZDIP": p_zdip}

    # ---- zona de amortecimento (Figura 8)
    g8, c8 = geos["fig8_za"], cores["fig8_za"]
    grade_za = Grade.da_figura(g8, res_za)
    # Num trecho a ZA acompanha a PR-560 e o traço laranja fica sob o vermelho da
    # rodovia; por isso o vermelho entra no contorno. Os ramos de rodovia que
    # sobram para fora são mais finos que o traço e somem ao descontar meia espessura.
    linha_za = grade_za.reamostrar(c8["laranja"] | c8["vermelho"], g8)
    za_total_m, espessura_za, pontes_za = interior_pela_linha_media(
        linha_za, grade_za.res, g8.pixel_m, ponte_max_m=320
    )
    za_total = grade_za.poligonizar(za_total_m, g8.pixel_m / 2)
    za_anel = za_total.difference(limite)

    # ---- gravação
    gpkg = saida / "zoneamento_vetorizado.gpkg"
    comum = {"fonte": FONTE, "provisorio": True}
    gpd.GeoDataFrame(
        [{"nome": "Parque Estadual de Santa Clara", "sigla": "PESC", **comum}],
        geometry=[limite],
        crs=EPSG_TRABALHO,
    ).to_file(gpkg, layer="limite_uc", driver="GPKG")
    gpd.GeoDataFrame(
        [{"sigla": s, "zona": ZONAS[s], **comum} for s in poligonos],
        geometry=list(poligonos.values()),
        crs=EPSG_TRABALHO,
    ).to_file(gpkg, layer="zoneamento", driver="GPKG")
    gpd.GeoDataFrame(
        [{"sigla": "ZA", "zona": "Zona de Amortecimento", **comum}],
        geometry=[za_anel],
        crs=EPSG_TRABALHO,
    ).to_file(gpkg, layer="zona_amortecimento", driver="GPKG")

    # ---- relatório: áreas e incerteza de digitalização (±1 pixel ao longo do perímetro)
    def resumo(geom, pixel: float) -> dict:
        return {
            "area_ha": round(geom.area / 1e4, 2),
            "perimetro_km": round(geom.length / 1e3, 2),
            "incerteza_ha": round(geom.length * pixel / 1e4, 2),
        }

    relatorio["limite_uc"] = {
        **resumo(limite, px),
        "espessura_traco_m": round(espessura, 1),
        "pontes_sobre_oclusoes_m": pontes,
        "area_por_figura_ha": areas_individuais,
        "desvio_padrao_entre_figuras_ha": round(
            float(np.std([a for a in areas_individuais.values() if a is not None], ddof=1)), 2
        ),
    }
    relatorio["zonas"] = {s: resumo(p, px) for s, p in poligonos.items()}
    relatorio["zonas"]["ZAA"]["area_pela_fig3_ha"] = round(float(m_zaa_fig3.sum()) * grade.res**2 / 1e4, 2)
    relatorio["zona_amortecimento"] = {
        **resumo(za_anel, g8.pixel_m),
        "area_com_a_uc_ha": round(za_total.area / 1e4, 2),
        "espessura_traco_m": round(espessura_za, 1),
        "pontes_sobre_oclusoes_m": pontes_za,
    }
    (saida / "relatorio_vetorizacao.json").write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    _conferencia(figs["fig3_zonas"], geos["fig3_zonas"], grade, {"ZAA": m_zaa, "ZI": m_zi, "ZDIP": m_zdip}, parque, saida / "conferencia_zonas.png")
    _conferencia(figs["fig8_za"], g8, grade_za, {}, za_total_m, saida / "conferencia_za.png")
    return relatorio


def _conferencia(rgb, geo: Georref, grade: Grade, zonas: dict, contorno: np.ndarray, destino: Path) -> None:
    """Desenha o resultado sobre a figura original para inspeção visual."""
    cores = {"ZAA": (255, 0, 255), "ZI": (255, 255, 0), "ZDIP": (255, 0, 0)}
    img = rgb.copy()
    lin, col = np.mgrid[0 : rgb.shape[0], 0 : rgb.shape[1]]
    gi = np.rint((grade.n_max - (geo.n0 + geo.dn * lin)) / grade.res - 0.5).astype(int)
    gj = np.rint(((geo.e0 + geo.de * col) - grade.e_min) / grade.res - 0.5).astype(int)
    ok = (gi >= 0) & (gi < grade.ny) & (gj >= 0) & (gj < grade.nx)

    def na_figura(mascara: np.ndarray) -> np.ndarray:
        saida = np.zeros(rgb.shape[:2], dtype=bool)
        saida[ok] = mascara[gi[ok], gj[ok]]
        return saida

    for sigla, m in zonas.items():
        borda = na_figura(m)
        borda = borda & ~ndimage.binary_erosion(borda)
        img[borda] = cores[sigla]
    dentro = na_figura(contorno)
    img[dentro & ~ndimage.binary_erosion(dentro)] = (0, 255, 255)
    Image.fromarray(img).save(destino)


def main() -> None:
    raiz = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pdf", type=Path, required=True, help="PDF do plano de manejo do PESC (IAT, 2026)")
    ap.add_argument("--saida", type=Path, default=raiz / "dados" / "processados" / "vetorizacao")
    args = ap.parse_args()
    relatorio = vetorizar(args.pdf, args.saida)
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
