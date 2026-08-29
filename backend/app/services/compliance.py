"""Validacao de compliance do conteudo do funil.

Enquanto os textos viviam em `app/bot/texts.py`, um teste varria o modulo e
garantia que nenhuma mensagem prometia ganho. Com o conteudo editavel pelo
painel, essa garantia precisa acontecer na ESCRITA: qualquer texto que entre
pela API passa por aqui antes de ser gravado.

Regra de origem: planejamento/regras.md — compliance jogos/apostas. Nenhuma
mensagem promete ganho financeiro, resultado garantido ou induz comportamento
compulsivo.
"""

import re
import unicodedata

#: Expressoes proibidas. Comparadas sobre o texto normalizado (sem acento,
#: minusculo, espacos colapsados), entao "Ganho Garantido" e "ganho  garantido"
#: caem na mesma regra.
TERMOS_PROIBIDOS: tuple[str, ...] = (
    "ganho garantido",
    "ganhos garantidos",
    "lucro certo",
    "lucro garantido",
    "dinheiro facil",
    "sem risco",
    "risco zero",
    "aposte agora",
    "renda garantida",
    "voce vai ganhar",
    "voce vai lucrar",
    "retorno garantido",
    "nunca perde",
    "sempre ganha",
    "multiplique seu dinheiro",
    "enriqueca",
    "fique rico",
)


def normalize(text: str) -> str:
    sem_acento = "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento)


def find_violations(text: str) -> list[str]:
    """Termos proibidos presentes no texto."""
    normalizado = normalize(text)
    return [termo for termo in TERMOS_PROIBIDOS if termo in normalizado]


class ComplianceError(ValueError):
    """Texto rejeitado por promessa de ganho."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        encontrados = ", ".join(f'"{v}"' for v in violations)
        super().__init__(
            f"o texto contem promessa de resultado ({encontrados}). "
            "Mensagens nao podem prometer ganho, lucro ou ausencia de risco."
        )


def assert_compliant(text: str) -> str:
    """Devolve o texto ou lanca ComplianceError. Usado como validador Pydantic."""
    violations = find_violations(text)
    if violations:
        raise ComplianceError(violations)
    return text
