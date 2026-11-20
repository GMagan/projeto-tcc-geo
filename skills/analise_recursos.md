---
id: analise_recursos
topico: "4.1"
titulo: Análise dos recursos e valores fundamentais
camada_ia: M2
tools: [listar_camadas, calcular_area, uso_solo_na_area, intersecao, distancia_ate, consultar_roteiro]
roteiro: "ICMBio (2018), p. 85-89"
---
# Skill: Análise dos recursos e valores fundamentais

## Papel
Para cada recurso e valor fundamental (RVF) da UC, montar o quadro do roteiro: condição atual,
ameaças, necessidades de dados e necessidades de planejamento. A parte mensurável da condição
atual e das ameaças vem das tools; o resto é rascunho para a oficina.

## Controle
Os RVFs são definidos na oficina de elaboração do plano. Eles vêm do usuário, na pergunta ou na
conversa; se não vierem, peça-os e não invente nenhum. As tools não dizem o estado de
conservação de uma espécie ou de um bem cultural: elas medem pressões sobre o território
(cobertura do solo, estradas, distância de estruturas). Use essas medidas como evidência e deixe
claro que a análise final é da oficina.

## Tools obrigatórias
- Camadas disponíveis: `listar_camadas`, para saber que evidência existe.
- Cobertura na UC: `uso_solo_na_area` com `camada='limite_uc'` (classes antrópicas = pressão; vegetação nativa = condição).
- Pressão do entorno: `uso_solo_na_area` com `camada='zona_amortecimento'`, se essa camada existir (lavoura e pastagem no entorno = ameaça de agrotóxico, fogo, exóticas).
- Estradas e outras linhas dentro da UC: `intersecao` com `camada_b='limite_uc'`.
- Distância de uma estrutura ou atrativo até outra camada: `distancia_ate`.
- Estrutura do quadro: `consultar_roteiro` com `consulta='análise dos recursos e valores fundamentais: condição atual, tendências, ameaças, necessidades de dados'`.

## Formato da saída
Um quadro por RVF, com as quatro partes: Condição atual, Ameaças, Necessidades de dados e
Necessidade de planejamento. O roteiro pede também a tendência do recurso; com um só retrato
do uso do solo ela não é medida: escreva "Tendência: (a validar na oficina)". Cada item medido
traz o valor, a unidade e a tool. Cada item não medido termina com "(a validar na oficina)". Se faltar a camada que mediria um item, ponha o
item em Necessidades de dados.

## Proibido
- Inventar RVF, espécie, atrativo ou bem cultural que o usuário não citou.
- Dar área, percentual ou distância sem chamar a tool.
- Apresentar ameaça não medida como fato.
