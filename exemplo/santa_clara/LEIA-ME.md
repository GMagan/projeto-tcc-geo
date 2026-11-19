# Exemplo: Parque Estadual de Santa Clara (PR)

Dados de demonstração. **O programa nunca usa esta pasta sozinho**: só quando alguém roda
`make exemplo`, que copia `entrada/` para `dados/entrada/` (e só se ela estiver vazia).

`entrada/` está no mesmo formato que um usuário entregaria:

| Arquivo | Origem |
|---|---|
| `zoneamento.gpkg`, `limite_uc.gpkg` | **Aproximados**: vetorizados das Figuras 3 a 8 do Plano de Manejo (IAT, 2026), pixel de ~5 m. Não são o shapefile oficial. |
| `municipios.gpkg` | IBGE, Malha Municipal 2024 (1:250.000) |
| `estradas`, `hidrografia`, `massas_dagua`, `edificacoes`, `linhas_transmissao`, `estruturas` | OpenStreetMap (ODbL) |
| `uso_solo.tif` + `uso_solo.csv` | ESA WorldCover 2021 v200 (CC BY 4.0) |
| `uc.yaml` | nome e sigla |
| `gabarito.yaml` | números publicados no plano (Tabelas 1 e 6) |

Como o zoneamento é aproximado, a comparação com o plano não bate na casa decimal: a área
da UC dá 616,66 ha contra 616,86 ha publicados, e as zonas internas divergem mais (as
figuras do plano não batem com a sua Tabela 6).

`origem/` guarda como estes dados foram montados: os scripts de download e de vetorização
(registro histórico; não fazem parte do programa e esperam os caminhos da época), o
relatório da vetorização e as somas SHA-256 dos downloads.
