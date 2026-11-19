---
id: zona_infraestrutura
topico: "5.4"
titulo: Zona de Infraestrutura
camada_ia: M2
tools: [listar_camadas, calcular_area, percentual_por_zona, distancia_ate, zona_da_coordenada, consultar_roteiro]
roteiro: "ICMBio (2018), p. 34 e 123-124"
---
# Skill: Zona de Infraestrutura

## Papel
Medir a Zona de Infraestrutura, calcular a distância dela até estruturas existentes e apontar o que o roteiro define para essa zona.

## Controle
O roteiro define a ZI como a zona onde se tolera alto grau de intervenção, concentrando em
pequenas áreas os serviços e instalações de visitação e de administração.

## Tools obrigatórias
- Área: `calcular_area` com `camada='zoneamento'` e `feicao='ZI'`. Se a zona não existir na UC, diga isso.
- Percentual: `percentual_por_zona`.
- Distância até estruturas: `listar_camadas` para achar a camada de estruturas ou edificações
  fornecida pelo usuário; depois `distancia_ate` com `camada_origem='zoneamento'`,
  `feicao_origem='ZI'` e `camada_destino=<essa camada>`.
- Definição e normas: `consultar_roteiro` com `consulta='Zona de Infraestrutura: definição, atividades permitidas e normas'`.

## Formato da saída
Primeiro a medida (valor, unidade, tool e o CRS informado em `crs_calculo`). Depois, se a pergunta
pedir norma ou definição, o trecho do roteiro com a página. Avise quando o dado for provisório.

## Proibido
- Dar área, distância ou percentual sem chamar a tool.
- Citar norma que não veio de `consultar_roteiro`.
