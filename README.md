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

Na primeira vez o `make` cria sozinho o ambiente Python (alguns minutos, ~1,1 GB). Depois:

1. importa `dados/entrada/`, perguntando no terminal o que faltar;
2. roda os testes;
3. calcula tabelas e mapas em `resultados/`.

Para ver funcionando antes de ter dados próprios: `make exemplo && make` (copia o exemplo
do PE Santa Clara para `dados/entrada/`; ver `exemplo/santa_clara/LEIA-ME.md`).

## Dois modos de importar: escolha um

| | `make` (modo normal) | `make ia` (modo IA) |
|---|---|---|
| Como reconhece os arquivos | regras fixas de nome e conteúdo (tabela abaixo) | a IA lê nomes, colunas e valores e diz o que é cada coisa |
| Exemplo | precisa de "municip" no nome do arquivo de municípios | entende `cidades.shp`, `areas_manejo.gpkg` com coluna `TIPO`... |
| Precisa de IA (Ollama)? | não | sim |

No modo IA a IA só **classifica**: diz qual arquivo é o zoneamento, qual coluna tem as zonas,
o que significa cada valor ("Núcleo intocável" = Zona de Preservação), qual arquivo são os
municípios, e o nome da UC se ele estiver escrito em algum arquivo. Ela não lê geometria nem
calcula nada. Contra alucinação, **tudo o que a IA disser é conferido contra os dados**:

- arquivo que não existe, coluna que não existe, valor de zona que não aparece no arquivo,
  sigla fora das 15 do roteiro, nome da UC que não está escrito em nenhum arquivo
  → **descartado** e mostrado na tela como "descartado";
- o que for obrigatório e não sobrar (zoneamento, nome da UC, significado de uma zona)
  → **perguntado** a você no terminal.

Antes de importar, o modo IA mostra o mapeamento e pede confirmação. Ele fica salvo em
`dados/entrada/mapeamento.yaml`: dá para conferir, editar à mão e rodar de novo; enquanto o
arquivo existir a IA não é chamada outra vez. Para pedir um mapeamento novo, apague o arquivo.
As regras que a IA segue estão em `skills/_importacao.md` (dá para ajustar sem mexer no código).
Depois da importação, os dois modos seguem iguais (mesmas contas, testes e resultados).

## O que colocar em `dados/entrada/`

Nomes de arquivo livres; subpastas valem. Vetores em `.shp` (com `.shx`, `.dbf` e `.prj`),
`.gpkg`, `.geojson` ou `.zip`, em qualquer sistema de coordenadas.
Um `.gpkg` com várias camadas ou um `.zip` com vários shapefiles conta como um arquivo por
camada, e as regras de nome abaixo olham o **nome da camada** (ex.: `projeto.gpkg` com a
camada `zoneamento`). Dois arquivos com o mesmo nome em subpastas diferentes viram camadas
com o nome da pasta na frente (ex.: `municipais_estradas`), com aviso.

| Dado | Obrigatório? | Como é reconhecido | Sem ele |
|---|---|---|---|
| **Zoneamento** | **sim** | arquivo com `zon` ou `amortec` no nome e uma coluna com o nome ou a sigla das zonas (ou com códigos numéricos traduzidos em `zonas.yaml`) | o programa para e pede; feição com a zona em branco fica de fora (avisado) |
| Nome e sigla da UC | sim | `uc.yaml` | o programa pergunta e salva em `uc.yaml` |
| Zona de amortecimento | não | feições "Zona de Amortecimento" no zoneamento (ou em outro arquivo) | sem área e mapa da ZA |
| Limite da UC | não | arquivo com `limite` ou `perimetro` no nome (e sem `municip`: `limites_municipais` são municípios) | o limite vira a união das zonas (avisado); limite muito maior que as zonas também é avisado |
| Municípios | não | arquivo com `municip` no nome; coluna de nome (ex.: `NM_MUN`). Pode ser a malha do Brasil inteiro: só ficam os municípios em volta da UC | sem municípios e percentuais da ficha técnica |
| Uso e cobertura do solo | não | raster `.tif` com `uso`, `cobertura` ou `mapbiomas` no nome; legenda em `.csv` de mesmo nome (código, classe; separado por `,` ou `;`, como o Excel grava) | sem `uso_solo_na_area`; sem legenda, classes saem pelo código |
| Outras camadas (estradas, rios, estruturas...) | não | qualquer outro vetor; vira camada com o nome do arquivo | distância e interseção só entre limite e zonas |
| `gabarito.yaml` | não | números publicados no plano (modelo abaixo) | sem comparação com o plano |

**Zonas reconhecidas** (as 14 do Roteiro Metodológico do ICMBio, 2018, mais a de
amortecimento), por nome ou sigla, sem diferenciar maiúscula e acento: ZP Preservação,
ZC Conservação, ZUR Uso Restrito, ZUM Uso Moderado, ZUC Uso Comunitário, ZMF Manejo
Florestal, ZI Infraestrutura, ZPO Populacional, ZPR Produção, ZUI Urbano-industrial,
ZST Sobreposição Territorial, ZDIP Diferentes Interesses Públicos, ZAA Adequação
Ambiental, ZUD Uso Divergente, ZA Amortecimento.
Nome parecido mas de outra zona não é adivinhado: "Zona de Interesse Histórico-Cultural" não
vira ZDIP, só "Interesses Públicos" vira.
Se o shapefile usar outro nome (ex.: "Z. Uso Público") ou um código, o programa pergunta qual
zona é e guarda a resposta em `dados/entrada/zonas.yaml`. Dá para escrever esse arquivo à mão
(`Z. Uso Público: ZUM`, `1: ZP`); sigla fora da lista acima para a importação.

**Sistema de referência:** os cálculos são feitos em SIRGAS 2000 / UTM, no **fuso da
própria UC**, escolhido a partir dos dados (ex.: EPSG:31982 no Paraná, EPSG:31980 em Manaus). O SIRGAS 2000
tem código só para os fusos 11N a 22N e 17S a 25S; UC fora deles (ex.: Ilha da Trindade, fuso
26S) faz a importação parar com aviso, em vez de calcular num sistema errado.

**Modelo de `gabarito.yaml`** (todas as chaves são opcionais). Escreva os números com **ponto decimal e sem separador de
milhar**, mesmo que o plano use vírgula: `1622.50`, e não `1.622,50`. Mantenha os zeros finais
do plano (`1622.50`, não `1622.5`).

```yaml
area_uc_ha: 616.86
perimetro_km: 13.77
municipios_percentual: {Candói: 51, Pinhão: 32}
extremos: {norte_lat: "25° 37' 46,846\"", oeste_lon: "51° 59' 22,879\""}
zonas_ha: {ZC: 538.37, ZAA: 70.42}
zona_amortecimento_ha: 1622.48
```

Extremos: a chave é `<norte|sul|leste|oeste>_<lat|lon>` e o valor vai em graus, minutos e
segundos entre aspas, como acima, ou em graus decimais (`norte_lat: -25.6297`). Nomes de
municípios e siglas de zonas são comparados sem diferenciar maiúscula e acento (`CANDOI` = `Candói`).
Um gabarito mal escrito (ex.: número com vírgula ou vazio) é avisado no fim do `make` e fica fora da comparação; o resto dos resultados sai.

A comparação é exata, nas casas que o plano publica: o valor calculado, arredondado assim, tem
de dar o número publicado. O que não bate aparece no fim do `make` e na tabela `gabarito` em `resultados/`.
Divergência não é erro do programa: mostra onde o arquivo e o texto do plano diferem.

## O que sai em `resultados/`

```
resumo.json             todos os valores e a resposta completa de cada ferramenta
tabelas/dados/          tabelas.json (ficha técnica, zonas, uso do solo, faixas, gabarito)
                        e numeros.json (área da UC, de cada zona etc.)
mapas/                  mapa de zoneamento e, se a UC tiver, da zona de amortecimento (PNG e PDF)
pytest.xml              resultado dos testes (sem ele, numeros.json traz "nao_rodou")
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

Opcional: um segundo modelo pode dar nota ao texto das respostas (tom, citação da fonte,
pertinência). `make juiz-llm JUIZ_MODELO=qwen2.5:14b` instala o DeepEval (~60 pacotes, só
nessa hora, via `requirements-juiz.txt`) e roda `evals/test_llm_quality.py` sobre os rastros
de `make avaliar-llm`. Sem `JUIZ_MODELO`, o teste é pulado.

## Outros comandos

```bash
make ajuda        # lista tudo
make servidor     # servidor MCP em http://localhost:8001/mcp (17 ferramentas)
make subir        # Open WebUI + servidor MCP em Docker (cp .env.example .env antes)
make diagramas    # diagramas SADT e de arquitetura em resultados/diagramas/
make juiz-llm     # nota do texto das respostas por um modelo juiz (ver parte 2)
make sync         # publica as skills como modelos no Open WebUI (rotas não testadas; ver scripts/sync_skills.py)
```

O `docker-compose.yml` fixa o Open WebUI na versão 0.6.31 (a primeira com cliente MCP). Para
trocar, mude a tag `image:` lá. No Open WebUI: Admin > Configurações > Ferramentas externas, tipo
**MCP (Streamable HTTP)**, URL `http://mcp-python:8001/mcp`.

## Planejamento e estado atual

O plano de manejo é tratado como um livro: 6 capítulos e 24 tópicos, na ordem do Roteiro
Metodológico do ICMBio (2018). Cada tópico é feito pela camada mais barata que dá conta dele:

| Camada | Quem faz | Para quê |
|---|---|---|
| T0 | só a ferramenta, sem IA | áreas, buffers, interseções, mapas |
| M1 | modelo pequeno/local (ex.: Qwen 2.5 7B) | extrair dados, preencher fichas |
| M2 | modelo médio com chamada de ferramentas | seguir a skill, conferir normas |
| M3 | modelo forte | redação analítica (propósito, questões-chave) |

Regra fixa: nenhum número sai do modelo; todo valor vem de uma ferramenta T0.

O TCC implementa os **9 tópicos que têm número publicado no plano** (dá para medir o erro). Os
outros 15 dependem de oficinas participativas ou de dados que o projeto ainda não lê, e ficam
planejados.

| Nº | Tópico | Camada | Estado |
|---|---|---|---|
| 1.1 | Levantamento de dados da UC | M1 | planejado (`buscar_documento`, `extrair_tabela_pdf`) |
| **1.2** | **Base cartográfica** | T0 | **feito**: `carregar_camada`, `validar_geometria`, `reprojetar` |
| 1.3 | Caracterização e resumo de gestão | M1 | planejado |
| 1.4 | Guia do participante da oficina | M1 | planejado |
| 2.1 | Contexto da elaboração | M1 | planejado |
| 2.2 | Elementos do plano | M1 | planejado |
| **3.1** | **Ficha técnica** | M1 + T0 | **feito**: `calcular_area`, `coordenadas_extremas`, `municipios_intersectados` |
| 3.2 | Propósito | M3 | planejado (depende da oficina) |
| 3.3 | Declarações de significância | M3 | planejado (`contar_especies_ameacadas`) |
| 3.4 | Recursos e valores fundamentais | M3 | planejado (depende da oficina) |
| 4.1 | Análise dos recursos e valores | M2 | planejado (`uso_solo_na_area` já existe) |
| 4.2 | Questões-chave | M3 | planejado (`sobrepor_propriedades`, CAR) |
| 4.3 | Necessidades de dados | M2 | planejado |
| **5.1** | **Distribuição das zonas** | M2 + T0 | **feito**: `calcular_area_zonas`, `percentual_por_zona` |
| **5.2** | **Zona de Conservação** | M2 + T0 | **feito**: `calcular_area`, `zona_da_coordenada`, `consultar_roteiro` |
| **5.3** | **Zona de Adequação Ambiental** | M2 + T0 | **feito**: `uso_solo_na_area` |
| **5.4** | **Zona de Infraestrutura** | M2 + T0 | **feito**: `distancia_ate` |
| **5.5** | **Zona de Diferentes Interesses Públicos** | M2 + T0 | **feito**: `intersecao` |
| **5.6** | **Zona de Amortecimento** | M2 + T0 | **feito**: `calcular_buffer`, `calcular_buffer_coordenada` |
| 5.7 | Normas gerais | M2 | planejado |
| 5.8 | Atos legais e administrativos | M1 | planejado |
| **6.1** | **Mapa de zoneamento** | T0 | **feito**: `gerar_mapa` (zoneamento e ZA) |
| 6.2 | Demais mapas temáticos (12) | T0 | planejado (`declividade`, `hipsometria`) |
| 6.3 | Listas de flora e fauna | M1 + T0 | planejado (`cruzar_lista_ameacadas`) |

**Feito e testado** (`make testes`, 117 testes):
- servidor MCP com 17 ferramentas, cada uma conferida contra geometria de resultado conhecido;
- importação nos dois modos (`make` e `make ia`), para qualquer UC, perguntando o que faltar;
- tabelas, mapas e comparação com o gabarito do plano (`make resultados`);
- consulta ao roteiro do ICMBio (BM25, com página para citação);
- 7 skills (ficha técnica, zoneamento e uma por zona), mais a persona e a skill de importação;
- orquestrador do agente, gerador de perguntas e juiz numérico.

**Feito, mas ainda não rodado de verdade:**
- avaliação com IA (`make avaliar-llm`, `avaliar-baseline`, `juiz-llm`) e modo IA da importação:
  testados só com um modelo de respostas fixas, nunca com o Ollama;
- `make subir` (Open WebUI + servidor MCP em Docker) e `make sync` (rotas não conferidas).

**Pendente:**
- rodar a avaliação com IA (qwen2.5:7b e llama3.2:3b, com e sem ferramentas);
- testar com os arquivos oficiais de outra UC. O exemplo de Santa Clara usa zoneamento
  vetorizado das figuras do plano (provisório) e por isso só 1 de 14 números do gabarito bate;
- telemetria com Langfuse (rastros e "curti/não curti" do Open WebUI): prevista no rascunho,
  fica fora do `docker-compose.yml` até ser ligada de fato;
- os 15 tópicos planejados acima.

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
requirements*.txt   dependências: -dev (tudo do `make`), -juiz (só `make juiz-llm`)
```
