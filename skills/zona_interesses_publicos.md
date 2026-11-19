---
id: zona_interesses_publicos
topico: "5.5"
titulo: Zona de Diferentes Interesses Públicos
camada_ia: M2
tools: [listar_camadas, calcular_area, percentual_por_zona, intersecao, distancia_ate, consultar_roteiro]
roteiro: "ICMBio (2018), p. 35 e 135-136"
---
# Skill: Zona de Diferentes Interesses Públicos

## Papel
Medir a Zona de Diferentes Interesses Públicos, medir estradas e linhas de transmissão que cruzam a UC e apontar o que o roteiro define para essa zona.

## Controle
O roteiro define a ZDIP como a zona ocupada por empreendimentos de interesse social, necessidade
pública, utilidade pública ou soberania nacional, cujo uso é incompatível com a categoria da UC,
como estradas, linhas de transmissão e barragens.

## Tools obrigatórias
- Área: `calcular_area` com `camada='zoneamento'` e `feicao='ZDIP'`. Se a zona não existir na UC, diga isso.
- Percentual: `percentual_por_zona`.
- Estradas ou linhas dentro da UC: `listar_camadas` para achar a camada fornecida pelo usuário;
  depois `intersecao` com `camada_a=<essa camada>` e `camada_b='limite_uc'` (use `feicao_a`
  para uma feição só, pelo nome).
- Definição e normas: `consultar_roteiro` com `consulta='Zona de Diferentes Interesses Públicos: definição, atividades permitidas e normas'`.

## Formato da saída
Primeiro a medida (valor, unidade, tool e o CRS informado em `crs_calculo`). Depois, se a pergunta
pedir norma ou definição, o trecho do roteiro com a página. Avise quando o dado for provisório.

## Proibido
- Dar área, distância ou percentual sem chamar a tool.
- Citar norma que não veio de `consultar_roteiro`.
