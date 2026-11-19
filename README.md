# projeto-tcc-geo

Agentes de IA para apoiar a elaboração do plano de manejo de **qualquer** unidade de
conservação (UC). O modelo de linguagem interpreta a pergunta e redige a resposta; **todo
número sai de ferramentas determinísticas** publicadas por um servidor MCP.

Nenhum dado de UC vem embutido: tudo vem do usuário. O que faltar, o programa pede.

## Como rodar

1. Instale os programas da seção [Instalar](#instalar) (uma vez por computador).
2. Coloque os dados da UC em `dados/entrada/`.
3. Na pasta do projeto, rode:

```bash
make
```

Na primeira vez o `make` cria sozinho o ambiente Python (alguns minutos, ~1,5 GB). Depois:

1. importa `dados/entrada/`, perguntando no terminal o que faltar;
2. roda os testes;
3. calcula tabelas e mapas em `resultados/`.

Para ver funcionando antes de ter dados próprios: `make exemplo && make` (copia o exemplo
do PE Santa Clara para `dados/entrada/`; ver `exemplo/santa_clara/LEIA-ME.md`).

## O que colocar em `dados/entrada/`

Nomes de arquivo livres; subpastas valem. Vetores em `.shp` (com `.shx`, `.dbf` e `.prj`),
`.gpkg`, `.geojson` ou `.zip`, em qualquer sistema de coordenadas.

| Dado | Obrigatório? | Como é reconhecido | Sem ele |
|---|---|---|---|
| **Zoneamento** | **sim** | uma coluna de texto com o nome ou a sigla das zonas | o programa para e pede |
| Nome e sigla da UC | sim | `uc.yaml` | o programa pergunta e salva em `uc.yaml` |
| Zona de amortecimento | não | feições "Zona de Amortecimento" no zoneamento (ou em outro arquivo) | sem área e mapa da ZA |
| Limite da UC | não | arquivo com `limite` ou `perimetro` no nome | o limite vira a união das zonas (avisado) |
| Municípios | não | arquivo com `municip` no nome; coluna de nome (ex.: `NM_MUN`) | sem municípios e percentuais da ficha técnica |
| Uso e cobertura do solo | não | raster `.tif`; legenda em `.csv` de mesmo nome (código, classe) | sem `uso_solo_na_area`; sem legenda, classes saem pelo código |
| Outras camadas (estradas, rios, estruturas...) | não | qualquer outro vetor; vira camada com o nome do arquivo | distância e interseção só entre limite e zonas |
| `gabarito.yaml` | não | números publicados no plano (modelo abaixo) | sem comparação com o plano |

**Zonas reconhecidas** (as 14 do Roteiro Metodológico do ICMBio, 2018, mais a de
amortecimento), por nome ou sigla, sem diferenciar maiúscula e acento: ZP Preservação,
ZC Conservação, ZUR Uso Restrito, ZUM Uso Moderado, ZUC Uso Comunitário, ZMF Manejo
Florestal, ZI Infraestrutura, ZPO Populacional, ZPR Produção, ZUI Urbano-industrial,
ZST Sobreposição Territorial, ZDIP Diferentes Interesses Públicos, ZAA Adequação
Ambiental, ZUD Uso Divergente, ZA Amortecimento.
Se o shapefile usar outro nome (ex.: "Z. Uso Público"), o programa pergunta qual zona é e
guarda a resposta em `dados/entrada/zonas.yaml`.

**Sistema de referência:** os cálculos são feitos em SIRGAS 2000 / UTM, no **fuso da
própria UC**, escolhido a partir dos dados (ex.: EPSG:31982 no Paraná, EPSG:31980 em Manaus).

**Modelo de `gabarito.yaml`** (todas as chaves são opcionais):

```yaml
area_uc_ha: 616.86
perimetro_km: 13.77
municipios_percentual: {Candói: 51, Pinhão: 32}
extremos: {norte_lat: "25° 37' 46,846\"", oeste_lon: "51° 59' 22,879\""}
zonas_ha: {ZC: 538.37, ZAA: 70.42}
zona_amortecimento_ha: 1622.48
```

A comparação é exata: o valor calculado, arredondado como no plano, tem de dar o número
publicado. O que não bate aparece no fim do `make` e na tabela `gabarito` em `resultados/`.
Divergência não é erro do programa: mostra onde o arquivo e o texto do plano diferem.

## O que sai em `resultados/`

```
resumo.json             todos os valores e a resposta completa de cada ferramenta
tabelas/dados/          tabelas.json (ficha técnica, zonas, uso do solo, faixas, gabarito)
                        e numeros.json (área da UC, de cada zona etc.)
mapas/                  mapa de zoneamento e da zona de amortecimento (PNG e PDF)
llm/                    rastros da avaliação com IA
auditoria_tools.jsonl   cada chamada de ferramenta feita pelo servidor MCP
```

## Instalar

| Programa | Para quê | Obrigatório? |
|---|---|---|
| Python 3.11+ com `venv` e `pip` | roda tudo | sim |
| `make` | o comando `make` | sim |
| Ollama | o modelo de linguagem do agente | sim, para a parte 2 (IA) |
| Docker + Compose | interface de chat (Open WebUI) | só para demonstração |

```bash
sudo apt install python3 python3-venv python3-pip make     # Ubuntu/Debian
sudo pacman -S python python-pip make                       # Arch
```

Windows: WSL2 com Ubuntu. GDAL, LaTeX e compilador não são necessários.

## Parte 2: avaliação do agente com IA (obrigatória para o TCC)

O `make` faz a **parte 1**: as contas, que por desenho não usam IA. A **parte 2** mede o
agente: se a IA chama a ferramenta certa e copia os números sem inventar, comparando com o
modelo sozinho. As perguntas são geradas a partir dos dados importados (zonas que existem,
um ponto dentro da maior zona, as camadas fornecidas e uma zona que a UC não tem).

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b      # ~4,7 GB, modelo principal
ollama pull llama3.2:3b     # ~2 GB, comparação com modelo pequeno

make avaliar-llm      LLM_MODELO=qwen2.5:7b    # agente com ferramentas
make avaliar-baseline LLM_MODELO=qwen2.5:7b    # modelo sozinho
make avaliar-llm      LLM_MODELO=llama3.2:3b
make avaliar-baseline LLM_MODELO=llama3.2:3b
make resultados                                # inclui a avaliação nas tabelas
```

O 7b precisa de ~8 GB de RAM livre; sem placa de vídeo, 1 a 3 min por pergunta.
Rode depois de importar os dados: as respostas certas dependem deles.
Ollama em outra máquina: `LLM_BASE_URL=http://IP:11434/v1`.

## Outros comandos

```bash
make ajuda        # lista tudo
make servidor     # servidor MCP em http://localhost:8001/mcp (17 ferramentas)
make subir        # Open WebUI + servidor MCP em Docker (cp .env.example .env antes)
make diagramas    # diagramas SADT e de arquitetura em resultados/diagramas/
```

No Open WebUI (>= 0.6.31): Admin > Configurações > Ferramentas externas, tipo
**MCP (Streamable HTTP)**, URL `http://mcp-python:8001/mcp`.

## Estrutura

```
dados/entrada/      <- dados da UC (do usuário)
dados/processados/  base gerada pelo importador (não editar)
dados/catalogo.yaml catálogo gerado pelo importador (não editar)
conhecimento/       Roteiro Metodológico do ICMBio indexado por página (consulta normativa)
mcp-python/         geotools/ (cálculos) + server.py (servidor MCP) + Dockerfile
skills/             persona e uma skill por tópico do plano (genéricas)
agente/             orquestrador: modelo <-> ferramentas, grava o rastro
evals/              testes, juiz numérico, comparação com o plano, avaliação com IA
scripts/            importar_dados, gerar_resultados, gerar_diagramas, sync_skills, construir_rag
exemplo/            PE Santa Clara, só para demonstração (`make exemplo`)
```
