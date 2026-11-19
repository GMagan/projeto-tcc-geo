---
id: zona_amortecimento
topico: "5.6"
titulo: Zona de Amortecimento
camada_ia: M2
tools: [calcular_area, calcular_buffer, intersecao, uso_solo_na_area, zona_da_coordenada, consultar_roteiro]
roteiro: "ICMBio (2018), p. 32 e 104-106"
---
# Skill: Zona de Amortecimento

## Papel
Medir a Zona de Amortecimento, compará-la com faixas de distância fixa em volta da UC, descrever o uso
do solo no entorno e apontar os critérios do roteiro.

## Controle
Pela Lei nº 9.985/2000, a zona de amortecimento é o entorno da UC onde as atividades humanas
seguem normas e restrições para reduzir impactos sobre a unidade. O roteiro lista os critérios
de delimitação (bacias que drenam para a UC, remanescentes de vegetação, conectividade).

## Tools obrigatórias
- Área da ZA: `calcular_area` com `camada='zona_amortecimento'` (se a camada não foi fornecida, diga isso).
- Faixa de distância fixa: `calcular_buffer` com `camada='limite_uc'` e `distancia_m`.
- Uso do solo no entorno: `uso_solo_na_area` com `camada='zona_amortecimento'`.
- Ponto dentro ou fora: `zona_da_coordenada`.
- Definição e critérios: `consultar_roteiro` com `consulta='zona de amortecimento: definição e critérios de delimitação'`.

## Formato da saída
Primeiro a medida (valor, unidade, tool e o CRS informado em `crs_calculo`). Depois, se a pergunta
pedir norma ou definição, o trecho do roteiro com a página. Avise quando o dado for provisório.

## Proibido
- Dar área, distância ou percentual sem chamar a tool.
- Citar norma que não veio de `consultar_roteiro`.
