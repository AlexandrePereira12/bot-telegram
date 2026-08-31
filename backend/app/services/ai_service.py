"""Atendimento por IA antes da fila humana.

Quando o lead escolhe falar com o time, quem responde primeiro e um modelo do
provedor configurado no painel — conversando normalmente, com o conteudo
cadastrado da campanha como base. A pessoa so entra quando o lead insiste em
falar com gente.

Sem integracao ativa cadastrada, nada disso existe: o funil continua mandando o
lead direto para a fila humana. A chave de API vem do banco, cifrada, e nao do
`.env` — trocar de chave e operacao de painel, nao de deploy.

Tres garantias que valem mais que a resposta em si:

- **A saida passa pela mesma validacao de compliance da API.** Texto com
  promessa de ganho nao chega ao Telegram. Num funil de apostas, soltar um
  gerador de texto sem essa checagem seria trocar a rede de protecao por sorte.
- **Falha nunca prende o lead.** Timeout, cota estourada (429 e comum em
  modelo gratuito) ou erro de rede caem no caminho de sempre: fila humana.
- **A IA nao finge ser humana.** O tom e natural, sem anunciar-se a cada
  mensagem, mas perguntou diretamente, ela responde a verdade. Isso esta no
  prompt, nao no codigo, porque e uma regra de conversa.

Sem SDK novo: `httpx` ja e dependencia do projeto. Cada provedor tem seu
formato — o Gemini usa `contents`/`systemInstruction`, o OpenRouter segue o
formato de chat completions — e a diferenca fica isolada nas duas funcoes de
chamada.
"""

from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    AiProvider,
    EventType,
    FunnelStep,
    MessageDirection,
    SenderType,
)
from app.core.logging import get_logger
from app.core.security import decrypt_secret
from app.models import AiIntegration, Campaign, Conversation, Message, TelegramUser
from app.services import content_service
from app.services.compliance import ComplianceError, assert_compliant
from app.services.event_service import record_event

logger = get_logger(__name__)

#: Frases que contam como pedido explicito de atendente humano. Compradas
#: contra o texto normalizado pelo modulo de compliance (sem acento, minusculo).
PEDIDOS_DE_HUMANO: tuple[str, ...] = (
    "falar com atendente",
    "falar com um atendente",
    "falar com uma pessoa",
    "falar com alguem",
    "falar com humano",
    "quero um atendente",
    "quero atendente",
    "atendimento humano",
    "me transfere",
    "transferir para",
    "chama alguem",
    "chamar alguem",
    "quero falar com gente",
    "pessoa de verdade",
    "sem robo",
    "nao quero robo",
    "e um robo",
    "e um bot",
)

SYSTEM_PROMPT = """Voce e atendente da {company} no Telegram e conversa em portugues do Brasil.

Como responder:
- Fale como uma pessoa do time: direto, cordial, sem formalidade excessiva.
- Respostas curtas, no maximo tres paragrafos. Nada de listas gigantes.
- Nunca invente politica, prazo, valor ou regra da empresa que nao esteja no
  material abaixo. Nao sabendo algo especifico da operacao, diga que vai
  confirmar com o time.
- Sobre o jogo em si e sobre apostas em geral, pode usar o que voce sabe.
- Se perguntarem diretamente se voce e uma IA, um robo ou um humano, responda a
  verdade: voce e um assistente automatico, e uma pessoa do time pode assumir a
  conversa quando o lead quiser.

Limites que nao se negociam:
- Nunca prometa ganho, lucro, retorno ou ausencia de risco. Nao diga que alguem
  vai ganhar, nem que existe estrategia que garanta resultado.
- Aposta e entretenimento pago e pode perder todo o valor. Lembre disso quando
  o assunto for dinheiro.
- Publico adulto: se houver sinal de que a pessoa e menor de {min_age} anos,
  diga que o servico e restrito e encerre o assunto.
- Nunca peca CPF, numero de documento, senha, codigo de verificacao ou foto de
  documento. Assunto de cadastro, saque travado ou conta bloqueada e caso para
  uma pessoa do time — ofereca transferir.
- Se a pessoa demonstrar perda de controle com o jogo, informe as ferramentas
  de limite e autoexclusao e cite o CVV (188, 24 horas, gratuito).

Material desta campanha — e a fonte sobre a nossa operacao, o produto e o que
a conversa oferece. Use o menu para orientar o lead ("posso te explicar X"), e
as respostas cadastradas como referencia do que dizemos oficialmente:

{base}"""


@dataclass(frozen=True)
class RespostaIA:
    """Resultado de uma rodada de atendimento por IA."""

    texto: str | None
    #: Motivo do fracasso, quando `texto` e None. So para log e evento.
    falha: str | None = None


def pede_humano(texto: str | None) -> bool:
    """Diz se a mensagem e um pedido explicito de atendente humano.

    Deteccao por frase, e nao por decisao do modelo: quem escolhe sair da IA e
    o lead, e esse gate nao pode depender justamente da parte que ele quer
    abandonar.
    """
    if not texto:
        return False
    from app.services.compliance import normalize

    normalizado = normalize(texto)
    return any(pedido in normalizado for pedido in PEDIDOS_DE_HUMANO)


async def _base_de_conhecimento(session: AsyncSession, campaign_id: int | None) -> str:
    """O que a IA sabe sobre esta operacao, montado do conteudo cadastrado.

    Nao e so a lista de respostas: entram tambem a campanha de onde o lead
    veio, a mensagem de boas-vindas (que e onde o produto e apresentado) e o
    menu completo, inclusive as opcoes sem resposta propria. Sem o menu, a IA
    nao sabe o que a conversa oferece e nao consegue dizer "posso te explicar o
    cash out"; sem as boas-vindas, ela nao sabe do que a campanha trata.

    Tudo vem do painel: editar uma etapa ou uma opcao muda o que a IA responde,
    sem tocar em codigo nem em prompt.
    """
    partes: list[str] = []

    if campaign_id is not None:
        campanha = await session.get(Campaign, campaign_id)
        if campanha is not None and campanha.tenant_id == settings.tenant_id:
            partes.append(
                f"# Campanha do lead\n"
                f"Nome: {campanha.name}\n"
                f"Origem: {campanha.source} / {campanha.platform}"
            )

    # Etapas que descrevem o produto e o atendimento. Consentimento e age gate
    # ficam de fora: sao texto legal, nao material de conversa.
    for etapa, titulo in (
        (FunnelStep.WELCOME, "Apresentacao enviada ao lead"),
        (FunnelStep.INFORMATION, "Mensagem padrao de informacao"),
        (FunnelStep.HUMAN_SUPPORT, "O que dizemos ao passar para uma pessoa"),
    ):
        conteudo = await content_service.get_content(session, etapa, campaign_id)
        if conteudo.body:
            partes.append(f"# {titulo}\n{conteudo.body}")

    opcoes = await content_service.get_options(session, campaign_id)
    if opcoes:
        menu = "\n".join(
            f"- {opcao.label}"
            + ("" if opcao.response() else " (leva direto para atendimento humano)")
            for opcao in opcoes
        )
        partes.append(f"# Assuntos que o menu oferece\n{menu}")

    for opcao in opcoes:
        resposta = opcao.response()
        if resposta is not None:
            partes.append(f"# {opcao.label}\n{resposta.body}")

    if not partes:
        return "(nenhum material cadastrado para esta campanha)"
    return "\n\n".join(partes)


async def _historico(
    session: AsyncSession, conversation: Conversation
) -> list[dict[str, str]]:
    """Ultimas mensagens da conversa no formato de chat.

    Mensagem do lead vira `user`; o que saiu daqui (bot, IA ou operador) vira
    `assistant` — do ponto de vista do modelo, tudo isso e "o que o atendimento
    ja disse".
    """
    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.tenant_id == settings.tenant_id,
        )
        .order_by(Message.id.desc())
        .limit(settings.ai_history_messages)
    )
    linhas = list((await session.execute(stmt)).scalars())
    linhas.reverse()

    mensagens: list[dict[str, str]] = []
    for linha in linhas:
        if not linha.content:
            # Anexo sem legenda nao vira turno vazio no prompt.
            continue
        papel = "user" if linha.direction == MessageDirection.INBOUND else "assistant"
        mensagens.append({"role": papel, "content": linha.content})
    return mensagens


async def integracao_ativa(session: AsyncSession) -> AiIntegration | None:
    """Integracao configurada e ligada deste tenant, se houver.

    E este o interruptor da funcionalidade: sem linha ativa, o atendimento por
    IA simplesmente nao existe para a instalacao.
    """
    stmt = select(AiIntegration).where(
        AiIntegration.tenant_id == settings.tenant_id,
        AiIntegration.is_active.is_(True),
    )
    return (await session.execute(stmt)).scalars().first()


async def disponivel(session: AsyncSession) -> bool:
    """Ha atendimento por IA nesta instalacao?

    Uma consulta por mensagem, indexada por tenant. Poderia ser cacheada, mas
    cache aqui significaria a IA continuar respondendo depois de alguem
    desligar a integracao no painel — e o interruptor precisa ser imediato.
    """
    return await integracao_ativa(session) is not None


async def _chamar_gemini(
    integracao: AiIntegration, system: str, historico: list[dict[str, str]], chave: str
) -> str:
    """Chamada ao Google Gemini (Generative Language API).

    Formato proprio: `contents` com `parts`, papel do assistente chamado
    `model`, e a instrucao de sistema num campo separado. A chave vai em header
    (`x-goog-api-key`), nunca em query string — URL com segredo vaza em log de
    proxy e em historico.

    O raciocinio e desligado nos modelos `flash`, e nao por economia: o teto de
    `maxOutputTokens` cobre raciocinio + resposta juntos, e medindo a chamada
    real o modelo gastava 476 tokens pensando para 13 de texto. Com teto de
    500, a resposta chegava vazia e o lead ia para a fila sem entender por que.
    Atendimento nao precisa de cadeia de raciocinio; precisa responder.
    """
    contents = [
        {
            "role": "model" if turno["role"] == "assistant" else "user",
            "parts": [{"text": turno["content"]}],
        }
        for turno in historico
    ]
    generation: dict = {
        "maxOutputTokens": settings.ai_max_tokens,
        "temperature": 0.6,
    }
    if "flash" in integracao.model.lower():
        # Só o flash aceita orcamento zero; no pro o minimo e 128 e mandar 0
        # seria 400. Nos outros, o teto maior ja da folga para os dois.
        generation["thinkingConfig"] = {"thinkingBudget": 0}

    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
        resposta = await client.post(
            f"{settings.gemini_base_url}/models/{integracao.model}:generateContent",
            headers={"x-goog-api-key": chave},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": contents,
                "generationConfig": generation,
            },
        )
        resposta.raise_for_status()
        corpo = resposta.json()

    candidatos = corpo.get("candidates") or []
    if not candidatos:
        # Sem candidato costuma ser bloqueio do filtro de seguranca do proprio
        # Gemini; o motivo vem em promptFeedback e ajuda a ajustar o prompt.
        motivo = (corpo.get("promptFeedback") or {}).get("blockReason", "desconhecido")
        raise ValueError(f"sem resposta do modelo (bloqueio: {motivo})")

    candidato = candidatos[0]
    partes = (candidato.get("content") or {}).get("parts") or []
    texto = "".join(parte.get("text", "") for parte in partes).strip()
    if not texto:
        # Diagnostico no proprio erro: "resposta vazia" nao diz se foi filtro
        # de seguranca, teto de tokens ou raciocinio comendo o orcamento.
        uso = corpo.get("usageMetadata") or {}
        raise ValueError(
            f"resposta sem texto (finishReason={candidato.get('finishReason')}, "
            f"raciocinio={uso.get('thoughtsTokenCount')}, "
            f"saida={uso.get('candidatesTokenCount')})"
        )
    return texto


async def _chamar_openrouter(
    integracao: AiIntegration, system: str, historico: list[dict[str, str]], chave: str
) -> str:
    """Chamada ao OpenRouter, no formato de chat completions."""
    mensagens = [{"role": "system", "content": system}, *historico]
    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
        resposta = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {chave}",
                "X-Title": f"{settings.company_name} - atendimento Telegram",
            },
            json={
                "model": integracao.model,
                "messages": mensagens,
                "max_tokens": settings.ai_max_tokens,
                "temperature": 0.6,
            },
        )
        resposta.raise_for_status()
        corpo = resposta.json()

    escolhas = corpo.get("choices") or []
    if not escolhas:
        raise ValueError(f"resposta sem choices: {str(corpo)[:200]}")
    texto = ((escolhas[0].get("message") or {}).get("content") or "").strip()
    if not texto:
        raise ValueError("resposta vazia")
    return texto


async def gerar(
    integracao: AiIntegration, system: str, historico: list[dict[str, str]]
) -> str:
    """Despacha para o provedor da integracao. Levanta em qualquer falha."""
    chave = decrypt_secret(integracao.api_key_encrypted)
    if integracao.provider == AiProvider.GEMINI:
        return await _chamar_gemini(integracao, system, historico, chave)
    return await _chamar_openrouter(integracao, system, historico, chave)


async def pedidos_de_humano(
    session: AsyncSession, user: TelegramUser, conversation: Conversation
) -> int:
    """Quantas vezes o lead pediu uma pessoa DURANTE o atendimento por IA.

    Conta eventos, e nao um contador em cache: o estado fica no banco, sobrevive
    a restart e aparece na linha do tempo do lead — da para auditar depois por
    que a conversa saiu da IA. O corte e o `started_at` da conversa, entao um
    atendimento novo comeca do zero.

    Escolher "falar com atendente" no menu nao entra na conta: e assim que se
    chega ao atendimento, e nao seria justo tratar a porta de entrada como
    insistencia — a IA nem teria chance de responder uma vez.
    """
    from sqlalchemy import func

    from app.models import Event

    # Corte no inicio deste ciclo de atendimento por IA. `started_at` da
    # conversa nao serve sozinho: um atendimento reaberto mantem o valor
    # original, e os pedidos do ciclo anterior fariam a IA escalar no primeiro
    # pedido do ciclo novo.
    inicio = (
        await session.execute(
            select(func.max(Event.created_at)).where(
                Event.tenant_id == settings.tenant_id,
                Event.telegram_user_id == user.id,
                Event.event_type == EventType.AI_SUPPORT_STARTED,
            )
        )
    ).scalar_one_or_none() or conversation.started_at

    stmt = select(func.count(Event.id)).where(
        Event.tenant_id == settings.tenant_id,
        Event.telegram_user_id == user.id,
        Event.event_type == EventType.AI_HANDOFF_REQUESTED,
    )
    if inicio is not None:
        stmt = stmt.where(Event.created_at >= inicio)
    return int((await session.execute(stmt)).scalar_one())


async def deve_escalar(
    session: AsyncSession, user: TelegramUser, conversation: Conversation
) -> bool:
    """A IA sai de cena quando o lead insiste em falar com gente."""
    return (
        await pedidos_de_humano(session, user, conversation)
        >= settings.ai_escalate_after_requests
    )


async def responder(
    session: AsyncSession,
    user: TelegramUser,
    conversation: Conversation,
    campaign_id: int | None,
    lead_id: int | None = None,
) -> RespostaIA:
    """Gera a proxima resposta do atendimento.

    Nao envia nem grava nada: devolve o texto para quem chamou decidir. Falha
    de qualquer natureza vira `RespostaIA(texto=None, falha=...)` — nunca
    excecao subindo para o handler, porque a conversa precisa continuar
    utilizavel mesmo com o provedor fora do ar.
    """
    integracao = await integracao_ativa(session)
    if integracao is None:
        return RespostaIA(texto=None, falha="sem_integracao")

    base = await _base_de_conhecimento(session, campaign_id)
    historico = await _historico(session, conversation)
    system = SYSTEM_PROMPT.format(
        company=settings.company_name, min_age=settings.min_age, base=base
    )

    try:
        texto = await gerar(integracao, system, historico)
    except httpx.HTTPStatusError as exc:
        motivo = f"http_{exc.response.status_code}"
        logger.warning(
            "provedor de IA recusou a chamada",
            extra={"event": "AI_FAILED", "reason": motivo},
        )
    except Exception as exc:
        # Mensagem, e nao so o tipo: "ValueError" nao diz nada a quem for
        # investigar por que o lead caiu na fila.
        motivo = f"{type(exc).__name__}: {exc}"[:200]
        logger.warning(
            "falha ao gerar resposta da IA",
            extra={"event": "AI_FAILED", "reason": motivo},
        )
    else:
        try:
            assert_compliant(texto)
        except ComplianceError as exc:
            # Nao escala e nao manda o texto: o lead recebe a mensagem de
            # indisponibilidade e a violacao fica no log, que e onde se decide
            # se o prompt precisa mudar.
            logger.warning(
                "resposta da IA recusada por compliance",
                extra={"event": "AI_BLOCKED", "terms": exc.violations},
            )
            await record_event(
                session,
                EventType.AI_FAILED,
                telegram_user_id=user.id,
                lead_id=lead_id,
                metadata={"reason": "compliance", "terms": exc.violations},
            )
            return RespostaIA(texto=None, falha="compliance")

        await record_event(
            session,
            EventType.AI_REPLIED,
            telegram_user_id=user.id,
            lead_id=lead_id,
            metadata={
                "provider": integracao.provider.value,
                "model": integracao.model,
                "chars": len(texto),
            },
        )
        return RespostaIA(texto=texto)

    await record_event(
        session,
        EventType.AI_FAILED,
        telegram_user_id=user.id,
        lead_id=lead_id,
        metadata={"reason": motivo},
    )
    return RespostaIA(texto=None, falha=motivo)


__all__ = [
    "RespostaIA",
    "SenderType",
    "deve_escalar",
    "pede_humano",
    "pedidos_de_humano",
    "responder",
]
