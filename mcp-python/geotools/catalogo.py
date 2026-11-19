"""Catálogo de camadas: a única porta de entrada dos dados para as tools."""
from __future__ import annotations

import unicodedata
from pathlib import Path

import geopandas as gpd
import yaml
from shapely import make_valid

from .erros import ErroGeo


def _normalizar(texto: object) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


class Catalogo:
    """Lê `catalogo.yaml` e entrega camadas já no CRS de trabalho.

    Trocar um dado provisório pelo oficial é editar o YAML; as tools não mudam.
    """

    def __init__(self, caminho_yaml: str | Path):
        self.caminho = Path(caminho_yaml)
        self._versao = self.caminho.stat().st_mtime_ns
        self.pasta = self.caminho.parent
        cfg = yaml.safe_load(self.caminho.read_text(encoding="utf-8"))
        self.epsg: int = int(cfg["crs_trabalho"])
        self.uc: dict = cfg.get("uc", {})
        self.camadas: dict[str, dict] = cfg.get("camadas", {})
        self.rasters: dict[str, dict] = cfg.get("rasters", {})
        self._cache: dict[tuple[str, bool], gpd.GeoDataFrame] = {}

    def recarregar_se_mudou(self) -> None:
        """Um `make importar` com o servidor no ar regrava o YAML: sem isto, o servidor serviria a UC antiga."""
        if self.caminho.stat().st_mtime_ns != self._versao:
            self.__init__(self.caminho)

    @property
    def crs(self) -> str:
        return f"EPSG:{self.epsg}"

    def meta(self, camada: str) -> dict:
        if camada not in self.camadas:
            raise ErroGeo(f"camada '{camada}' não existe; camadas disponíveis: {', '.join(sorted(self.camadas))}")
        return self.camadas[camada]

    def meta_raster(self, raster: str) -> dict:
        if raster not in self.rasters:
            raise ErroGeo(f"raster '{raster}' não existe; rasters disponíveis: {', '.join(sorted(self.rasters))}")
        return self.rasters[raster]

    def caminho_raster(self, raster: str) -> Path:
        return self.pasta / self.meta_raster(raster)["arquivo"]

    def ler(self, camada: str, *, no_crs_de_trabalho: bool = True) -> gpd.GeoDataFrame:
        """Camada como GeoDataFrame; por padrão reprojetada e com geometrias válidas."""
        chave = (camada, no_crs_de_trabalho)
        if chave not in self._cache:
            meta = self.meta(camada)
            arquivo = self.pasta / meta["arquivo"]
            if not arquivo.exists():
                raise ErroGeo(f"arquivo da camada '{camada}' não encontrado: {arquivo}")
            gdf = gpd.read_file(arquivo, layer=meta.get("camada"))
            if gdf.crs is None:
                raise ErroGeo(f"camada '{camada}' não declara sistema de referência (CRS)")
            # a procedência gravada no dado (ex.: shapefile oficial importado) vale mais que a do YAML
            if "provisorio" in gdf and len(gdf):
                meta["provisorio"] = bool(gdf["provisorio"].astype(bool).any())
            if "fonte" in gdf and len(gdf) and str(gdf["fonte"].iloc[0]).strip():
                meta["fonte"] = str(gdf["fonte"].iloc[0])
            if no_crs_de_trabalho:
                gdf = gdf.to_crs(self.epsg)
                gdf["geometry"] = gdf.geometry.apply(make_valid)
            self._cache[chave] = gdf
        return self._cache[chave].copy()

    def rotulos(self, camada: str) -> list[str]:
        """Siglas (ou nomes) das feições, para mensagens e listagens."""
        meta, gdf = self.meta(camada), self.ler(camada)
        campo = meta.get("campo_sigla") or meta.get("campo_nome")
        return [str(v) for v in gdf[campo]] if campo and campo in gdf else []

    def selecionar(self, camada: str, feicao: str = "") -> gpd.GeoDataFrame:
        """Feições da camada; `feicao` filtra por sigla ou nome (sem diferenciar acento e caixa)."""
        gdf = self.ler(camada)
        if not feicao:
            return gdf
        meta = self.meta(camada)
        alvo = _normalizar(feicao)
        for campo in (meta.get("campo_sigla"), meta.get("campo_nome")):
            if campo and campo in gdf:
                achadas = gdf[gdf[campo].map(_normalizar) == alvo]
                if len(achadas):
                    return achadas
        raise ErroGeo(
            f"feição '{feicao}' não existe na camada '{camada}'; opções: {', '.join(self.rotulos(camada)) or '(sem rótulos)'}"
        )

    def procedencia(self, *camadas: str) -> dict:
        """Fonte de cada camada usada e se alguma delas é provisória."""
        for c in camadas:
            if c in self.camadas:
                self.ler(c)  # carrega a procedência gravada no dado
        metas = {c: (self.camadas.get(c) or self.rasters.get(c) or {}) for c in camadas}
        saida = {
            "fontes": {c: m.get("fonte", "") for c, m in metas.items()},
            "provisorio": any(m.get("provisorio", False) for m in metas.values()),
        }
        if saida["provisorio"]:
            saida["aviso"] = "resultado calculado sobre dado provisório; refazer com o shapefile oficial"
        return saida
