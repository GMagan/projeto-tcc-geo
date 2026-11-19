---
id: ficha_tecnica
topico: "3.1"
titulo: Breve descrição e ficha técnica
camada_ia: M2
tools: [listar_camadas, calcular_area, coordenadas_extremas, municipios_intersectados, carregar_camada]
roteiro: "ICMBio (2018), seção 6.6.1 (conteúdo do plano de manejo)"
---
# Skill: Breve descrição e ficha técnica

## Papel
Preencher os campos espaciais da ficha técnica: superfície, perímetro, municípios abrangidos e
coordenadas extremas.

## Controle
A ficha técnica abre os componentes fundamentais do plano. A superfície e o perímetro são os do
limite da UC (camada `limite_uc`).

## Tools obrigatórias
- Superfície e perímetro: `calcular_area` com `camada='limite_uc'`.
- Municípios e percentuais: `municipios_intersectados` (se a camada de municípios não foi
  fornecida, diga que o usuário precisa carregá-la).
- Coordenadas extremas: `coordenadas_extremas`.

## Formato da saída
Uma linha por campo: nome do campo, valor com unidade. Feche com a tool e o CRS.

## Proibido
- Informar área ou percentual sem chamar a tool.
- Completar campo sem dado com informação de memória.
