---
id: zoneamento
topico: "5.1"
titulo: Distribuição das zonas
camada_ia: M2
tools: [calcular_area_zonas, percentual_por_zona, calcular_area, zona_da_coordenada, uso_solo_na_area, consultar_roteiro]
roteiro: "ICMBio (2018), seções 3.3.1 e 6.5.3.1 (p. 30-36 e 97-104)"
---
# Skill: Distribuição das zonas

## Papel
Montar a tabela de zonas da UC: área em hectares e percentual de cada zona, total e Zona de
Amortecimento à parte. Responder também sobre qualquer zona que não tenha skill própria.

## Controle
Pelo roteiro, zoneamento é a divisão da UC em setores com objetivos de manejo e normas
próprios. As zonas internas têm de cobrir a UC inteira, sem sobra e sem sobreposição. A
Zona de Amortecimento fica fora da UC e não entra no total. As zonas existentes nesta UC
são as que `calcular_area_zonas` devolve; não suponha outras.

## Tools obrigatórias
- Áreas e conferência com o limite: `calcular_area_zonas`.
- Percentuais: `percentual_por_zona`.
- Área de uma zona: `calcular_area` com `camada='zoneamento'` e `feicao=<sigla>`.
- Zona de um ponto: `zona_da_coordenada` (lon e lat em graus decimais).
- Uso do solo numa zona: `uso_solo_na_area` com `camada='zoneamento'` e `feicao=<sigla>`.
- Definição de uma zona: `consultar_roteiro` com `consulta='<nome da zona>: definição, atividades permitidas e normas'`.

## Formato da saída
Tabela com as colunas Zona, Área (ha) e %. Depois, uma linha com o total e outra com a Zona
de Amortecimento. Se `diferenca_para_o_limite_ha` ou `sobreposicao_entre_zonas_ha` não for
zero, avise. Se a zona perguntada não existir na UC, diga isso.

## Proibido
- Calcular percentual ou total por conta própria.
- Incluir a Zona de Amortecimento no total da UC.
- Dar área de zona que não existe nesta UC.
