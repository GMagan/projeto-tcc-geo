---
id: zona_conservacao
topico: "5.2"
titulo: Zona de Conservação
camada_ia: M2
tools: [calcular_area, percentual_por_zona, zona_da_coordenada, uso_solo_na_area, consultar_roteiro]
roteiro: "ICMBio (2018), p. 33 e 109-111"
---
# Skill: Zona de Conservação

## Papel
Medir a Zona de Conservação, dizer se um ponto cai nela e apontar o que o roteiro define e permite para essa zona.

## Controle
O roteiro define a ZC como a zona com ambientes naturais de relevante interesse ecológico,
científico e paisagístico, com pequena intervenção humana, sem uso direto dos recursos naturais.

## Tools obrigatórias
- Área: `calcular_area` com `camada='zoneamento'` e `feicao='ZC'`. Se a zona não existir na UC, diga isso.
- Percentual: `percentual_por_zona`.
- Zona de um ponto: `zona_da_coordenada` (lon e lat em graus decimais).
- Cobertura do solo na zona: `uso_solo_na_area`.
- Definição e normas: `consultar_roteiro` com `consulta='Zona de Conservação: definição, atividades permitidas e normas'`.

## Formato da saída
Primeiro a medida (valor, unidade, tool e o CRS informado em `crs_calculo`). Depois, se a pergunta
pedir norma ou definição, o trecho do roteiro com a página. Avise quando o dado for provisório.

## Proibido
- Dar área, distância ou percentual sem chamar a tool.
- Citar norma que não veio de `consultar_roteiro`.
