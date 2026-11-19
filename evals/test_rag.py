"""Testes da consulta ao roteiro metodológico (controle normativo via RAG)."""
from __future__ import annotations

import geotools as gt

TRECHOS = [
    {"fonte": "Roteiro ICMBio (2018)", "pagina": 33, "texto": "Zona de Conservação: é a zona que contém ambientes naturais de relevante interesse ecológico, onde tenha ocorrido pequena intervenção humana."},
    {"fonte": "Roteiro ICMBio (2018)", "pagina": 34, "texto": "Zona de Infraestrutura: é a zona onde é tolerado um alto grau de intervenção no ambiente, concentrando serviços e instalações."},
    {"fonte": "Roteiro ICMBio (2018)", "pagina": 32, "texto": "A zona de amortecimento é o entorno de uma unidade de conservação, onde as atividades humanas estão sujeitas a normas e restrições específicas."},
    {"fonte": "Roteiro ICMBio (2018)", "pagina": 80, "texto": "O propósito da unidade de conservação identifica os motivos específicos para sua criação."},
]


def test_consulta_traz_primeiro_o_trecho_que_trata_do_assunto():
    r = gt.consultar_roteiro(gt.IndiceBM25(TRECHOS), "alto grau de intervenção e instalações", k=2)
    assert r["trechos"][0]["pagina"] == 34
    assert len(r["trechos"]) <= 2


def test_consulta_ignora_acentos_e_caixa():
    r = gt.consultar_roteiro(gt.IndiceBM25(TRECHOS), "ZONA DE AMORTECIMENTO entorno restricoes", k=1)
    assert r["trechos"][0]["pagina"] == 32


def test_cada_trecho_informa_fonte_pagina_e_pontuacao_decrescente():
    r = gt.consultar_roteiro(gt.IndiceBM25(TRECHOS), "zona conservação ambientes naturais", k=3)
    pontos = [t["pontuacao"] for t in r["trechos"]]
    assert pontos == sorted(pontos, reverse=True)
    assert all(t["fonte"] == "Roteiro ICMBio (2018)" and t["pagina"] for t in r["trechos"])


def test_consulta_sem_termo_conhecido_devolve_lista_vazia():
    r = gt.consultar_roteiro(gt.IndiceBM25(TRECHOS), "criptomoeda blockchain", k=3)
    assert r["trechos"] == []
    assert r["status"] == "sucesso"
