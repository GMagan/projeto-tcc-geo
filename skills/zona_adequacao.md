---
id: zona_adequacao
topico: "5.3"
titulo: Zona de Adequação Ambiental
camada_ia: M2
tools: [calcular_area, percentual_por_zona, uso_solo_na_area, zona_da_coordenada, consultar_roteiro]
roteiro: "ICMBio (2018), p. 35 e 136-138"
---
# Skill: Zona de Adequação Ambiental

## Papel
Medir a Zona de Adequação Ambiental, descrever o uso do solo dentro dela e apontar o que o roteiro define para essa zona.

## Controle
O roteiro define a ZAA como zona de áreas consideravelmente antropizadas, onde é preciso deter
a degradação, recuperar o ambiente e erradicar ou controlar espécies exóticas. É uma zona
provisória: recuperada, passa a integrar uma zona permanente. O uso do solo dentro dela mostra
o quanto falta recuperar.

## Tools obrigatórias
- Área: `calcular_area` com `camada='zoneamento'` e `feicao='ZAA'`. Se a zona não existir na UC, diga isso.
- Percentual: `percentual_por_zona`.
- Uso do solo: `uso_solo_na_area` com `camada='zoneamento'` e `feicao='ZAA'`.
- Definição e normas: `consultar_roteiro` com `consulta='Zona de Adequação Ambiental: definição, atividades permitidas e normas'`.

## Formato da saída
Primeiro a medida (valor, unidade, tool e o CRS informado em `crs_calculo`). Depois, se a pergunta
pedir norma ou definição, o trecho do roteiro com a página. Avise quando o dado for provisório.

## Proibido
- Dar área, distância ou percentual sem chamar a tool.
- Citar norma que não veio de `consultar_roteiro`.
