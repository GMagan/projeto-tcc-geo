"""Leitura das skills (Markdown com cabeçalho YAML) e montagem do prompt de sistema."""
from __future__ import annotations

from pathlib import Path

import yaml

PASTA = Path(__file__).resolve().parents[1] / "skills"


def carregar_skill(ident: str, pasta: Path = PASTA) -> dict:
    """Lê skills/<ident>.md: o cabeçalho vira metadados e o corpo, o texto da skill."""
    bruto = (pasta / f"{ident}.md").read_text(encoding="utf-8")
    _, cabecalho, corpo = bruto.split("---", 2)
    skill = yaml.safe_load(cabecalho)
    skill["texto"] = corpo.strip()
    return skill


def listar_skills(pasta: Path = PASTA) -> list[str]:
    return sorted(p.stem for p in pasta.glob("*.md") if not p.name.startswith("_"))


def montar_prompt(skill: dict, pasta: Path = PASTA) -> str:
    """Prompt de sistema = persona (controle geral) + skill (controle da tarefa)."""
    persona = (pasta / "_persona.md").read_text(encoding="utf-8").strip()
    return f"{persona}\n\n---\n\n{skill['texto']}"
