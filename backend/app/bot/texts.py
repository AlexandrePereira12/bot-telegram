"""Textos do bot.

Regra de compliance (planejamento/regras.md): nenhuma mensagem promete ganho
financeiro, resultado garantido ou induz comportamento compulsivo. Qualquer
texto novo passa pela mesma revisao — e por test_message_templates.py, que
falha se aparecer termo proibido.
"""

from app.core.config import settings

WELCOME = (
    "Ola{name}! Bem-vindo(a) a {company}.\n\n"
    "Antes de continuar, precisamos de dois passos rapidos: confirmar o aceite "
    "dos termos e verificar sua idade."
)

CONSENT = (
    "**Termos e privacidade (versao {version})**\n\n"
    "Para seguir, precisamos do seu aceite para tratar seus dados e enviar "
    "mensagens sobre este atendimento. Voce pode revogar quando quiser "
    "enviando /parar.\n\n"
    "Voce aceita?"
)

CONSENT_REQUIRED = (
    "Sem o aceite dos termos nao conseguimos continuar. "
    "Se mudar de ideia, envie /start novamente."
)

AGE_GATE = (
    "Este conteudo e restrito a maiores de {min_age} anos.\n\n"
    "Voce confirma que tem {min_age} anos ou mais?"
)

AGE_REJECTED = (
    "Obrigado pela honestidade. Este conteudo e restrito a maiores de "
    "{min_age} anos, entao encerramos por aqui."
)

AGE_BLOCKED = (
    "Este conteudo e restrito a maiores de {min_age} anos e nao podemos "
    "continuar o atendimento."
)

QUALIFICATION = (
    "Perfeito. Para direcionar melhor, o que voce procura agora?"
)

INFORMATION = (
    "Certo! Reunimos as informacoes sobre *{interest}*.\n\n"
    "Se preferir falar com uma pessoa do time, e so tocar no botao abaixo."
)

HUMAN_SUPPORT = (
    "Voce entrou na fila de atendimento. Uma pessoa do time responde por aqui "
    "assim que possivel."
)

UNDER_HUMAN_SUPPORT = (
    "Sua mensagem foi registrada e o time ja esta com o seu atendimento."
)

CONSENT_REVOKED = (
    "Pronto. Seu consentimento foi revogado e nao enviaremos mais mensagens. "
    "Envie /start se quiser retomar."
)

BLOCKED = "Este atendimento esta encerrado."

FALLBACK = (
    "Nao entendi. Use os botoes da conversa ou envie /start para recomecar."
)

HELP = (
    "Comandos disponiveis:\n"
    "/start - iniciar ou retomar o atendimento\n"
    "/status - ver em que etapa voce esta\n"
    "/parar - revogar consentimento e parar mensagens\n"
    "/ajuda - esta mensagem"
)

FOLLOWUP = (
    "Voce ficou por aqui ha pouco e nao concluiu. "
    "Se ainda quiser continuar, e so responder esta mensagem."
)


def welcome(first_name: str | None) -> str:
    name = f", {first_name}" if first_name else ""
    return WELCOME.format(name=name, company=settings.company_name)


def consent() -> str:
    return CONSENT.format(version=settings.consent_version)


def age_gate() -> str:
    return AGE_GATE.format(min_age=settings.min_age)


def age_rejected() -> str:
    return AGE_REJECTED.format(min_age=settings.min_age)


def age_blocked() -> str:
    return AGE_BLOCKED.format(min_age=settings.min_age)


def information(interest: str) -> str:
    return INFORMATION.format(interest=interest)


#: Interesses oferecidos na qualificacao. Rotulo -> chave gravada no lead.
INTERESTS: dict[str, str] = {
    "Conhecer o servico": "service_info",
    "Tirar duvidas": "faq",
    "Falar com atendente": "human_support",
}
