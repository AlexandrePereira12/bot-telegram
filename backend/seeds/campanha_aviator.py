"""Semeia uma campanha de demonstracao com o funil completo do Aviator.

Serve para testar o caminho inteiro com conteudo realista antes de existir
trafego de verdade: varias direcoes de informacao, cada uma com sua resposta e
sua imagem, e uma unica porta para o atendimento humano.

O conteudo e FICTICIO e escrito para exercitar o funil, nao para publicar. Ele
passa pela mesma validacao de compliance da API (`assert_compliant`) antes de
qualquer escrita: se um texto prometer ganho, o seed falha aqui em vez de
gravar no banco algo que a rota recusaria.

Uso, dentro do container da API:

    docker compose exec -T api python -m seeds.campanha_aviator --campaign-id 1

Sem `--campaign-id`, procura uma campanha chamada "Campanha de teste". O seed
e idempotente: rodar duas vezes deixa o mesmo estado, sem duplicar opcao nem
acumular midia orfa.
"""

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.enums import FunnelStep, MediaType, OptionTarget
from app.models import Campaign, FunnelContent, QualificationOption
from app.services import media_service
from app.services.compliance import assert_compliant

IMAGENS = Path(__file__).parent / "imagens"

# --------------------------------------------------------------------- textos
#
# Regra que guiou a escrita: descrever a mecanica e o risco, nunca sugerir
# resultado. "Pode perder o valor" aparece mais de uma vez de proposito — e o
# que separa material informativo de anuncio de aposta.

ETAPAS: dict[FunnelStep, tuple[str, str | None]] = {
    FunnelStep.WELCOME: (
        "Ola{name}! Aqui e o canal de informacoes do Aviator na {company}.\n\n"
        "O jogo e simples de entender e rapido de jogar: um multiplicador sobe "
        "enquanto o aviao voa, e a rodada termina quando ele vai embora. "
        "Quem retira antes fica com o multiplicador do momento; quem nao "
        "retira a tempo perde o valor daquela rodada.\n\n"
        "Antes de continuar, preciso do seu aceite dos termos.",
        "aviator-rodada.jpg",
    ),
    FunnelStep.QUALIFICATION: (
        "Certo! Sobre o que voce quer saber primeiro?\n\n"
        "Escolha uma opcao abaixo — da para ver quantas quiser antes de falar "
        "com alguem do time.",
        None,
    ),
    FunnelStep.INFORMATION: (
        "Reuni o que temos sobre *{interest}*.\n\n"
        "Quer ver outro assunto ou prefere falar com uma pessoa do time? "
        "E so escolher no menu.",
        None,
    ),
    # Abertura do atendimento automatico. So aparece quando ha integracao de
    # IA ativa (Configuracoes no painel); sem ela, o lead vai direto para a
    # mensagem de fila abaixo.
    FunnelStep.AI_SUPPORT: (
        "Opa! Sou do atendimento da {company} e consigo te ajudar por aqui "
        "mesmo.\n\n"
        "Me conta o que voce precisa: duvida sobre a rodada, deposito, saque "
        "ou cadastro. Se preferir falar com outra pessoa do time, e so pedir.",
        None,
    ),
    FunnelStep.HUMAN_SUPPORT: (
        "Voce entrou na fila de atendimento. Uma pessoa do time assume esta "
        "conversa e responde por aqui mesmo.\n\n"
        "Se puder, ja adianta o que aconteceu: conta, deposito, saque ou "
        "duvida sobre a rodada. Assim a primeira resposta ja vem util.",
        "aviator-atendimento.jpg",
    ),
    FunnelStep.FOLLOWUP: (
        "Voce comecou a ver as informacoes por aqui e parou no meio. Se ainda "
        "fizer sentido, e so mandar qualquer mensagem que eu retomo de onde "
        "voce estava.\n\n"
        "Se preferir nao receber mais mensagens, envie /parar.",
        None,
    ),
}

# ------------------------------------------------------------------- opcoes
#
# Seis direcoes informativas antes da unica porta para o atendimento humano.
# A variedade e proposital: com midia e sem midia, resposta curta e resposta
# longa, assunto de produto e assunto de compliance — e o que faz o teste
# cobrir o funil em vez de um caminho so.

OPCOES: list[dict] = [
    {
        "key": "como_funciona",
        "label": "Como o jogo funciona",
        "sort_order": 10,
        "response_body": (
            "*Como funciona uma rodada*\n\n"
            "1. Voce entra na rodada antes da decolagem.\n"
            "2. O multiplicador comeca em 1.00x e sobe enquanto o aviao voa.\n"
            "3. Se retirar durante o voo, vale o multiplicador daquele instante.\n"
            "4. Se o aviao for embora antes da retirada, a rodada se encerra e "
            "o valor daquela entrada e perdido.\n\n"
            "O momento em que a rodada termina e sorteado a cada partida e nao "
            "da para prever pelo historico: rodadas anteriores nao influenciam "
            "a proxima."
        ),
        "media": "aviator-como-funciona.jpg",
    },
    {
        "key": "cash_out",
        "label": "O que e a retirada (cash out)",
        "sort_order": 20,
        "response_body": (
            "*Retirada*\n\n"
            "Retirar e encerrar a sua participacao na rodada em andamento. O "
            "valor da entrada e multiplicado pelo numero que estiver na tela "
            "no momento do toque.\n\n"
            "Da para programar uma retirada automatica num multiplicador "
            "escolhido — util para nao depender do reflexo. Mesmo com a "
            "retirada automatica, a rodada pode terminar antes do numero "
            "escolhido, e nesse caso a entrada e perdida."
        ),
        "media": "aviator-cash-out.jpg",
    },
    {
        "key": "modo_demo",
        "label": "Testar sem dinheiro",
        "sort_order": 30,
        "response_body": (
            "*Modo demonstracao*\n\n"
            "Da para rodar com saldo ficticio, com as mesmas regras da rodada "
            "valendo. Nenhum valor real entra ou sai no modo demonstracao.\n\n"
            "E o caminho recomendado para entender a mecanica antes de decidir "
            "qualquer coisa. Vale lembrar que o resultado no modo "
            "demonstracao nao indica o que acontece com valor real."
        ),
        "media": "aviator-demo.jpg",
    },
    {
        "key": "pagamentos",
        "label": "Deposito e saque",
        "sort_order": 40,
        "response_body": (
            "*Deposito e saque*\n\n"
            "O Pix e o meio principal nos dois sentidos. A chave usada no "
            "saque precisa ser do mesmo CPF cadastrado na conta — transferencia "
            "para terceiros nao e liberada.\n\n"
            "O saque passa por conferencia de cadastro antes de sair. Se algo "
            "travar, o time consegue olhar o caso pelo atendimento."
        ),
        "media": "aviator-pagamentos.jpg",
    },
    {
        "key": "jogo_responsavel",
        "label": "Limites e jogo responsavel",
        "sort_order": 50,
        "response_body": (
            "*Limites e controle*\n\n"
            "Aposta e entretenimento pago, nao fonte de renda: entra apenas o "
            "valor que voce pode perder por completo.\n\n"
            "Ferramentas disponiveis antes de qualquer rodada:\n"
            "- limite de valor por dia;\n"
            "- aviso e encerramento por tempo de sessao;\n"
            "- autoexclusao temporaria ou definitiva.\n\n"
            "Se o jogo estiver atrapalhando sono, trabalho ou dinheiro de "
            "contas, procure ajuda: o CVV atende em 188, 24 horas, gratuito."
        ),
        "media": "aviator-limites.jpg",
    },
    {
        "key": "conta_documentos",
        "label": "Cadastro e verificacao",
        "sort_order": 60,
        # Sem imagem de proposito: exercita o caminho da resposta so com texto.
        "response_body": (
            "*Cadastro e verificacao*\n\n"
            "A conta e pessoal e intransferivel, aceita apenas para maiores de "
            "18 anos, e exige documento com foto e selfie na verificacao.\n\n"
            "Nome, CPF e data de nascimento precisam bater com o documento. "
            "Cadastro com dado divergente fica bloqueado para saque ate a "
            "correcao."
        ),
        "media": None,
    },
    {
        "key": "falar_atendente",
        "label": "Falar com atendente",
        "sort_order": 70,
        "target": OptionTarget.HUMAN_SUPPORT,
        # Sem resposta propria: quem escolhe esta opcao recebe a mensagem da
        # etapa HUMAN_SUPPORT e entra na fila.
        "response_body": None,
        "media": None,
    },
]


async def _midia(session, arquivo: str | None) -> tuple[int | None, MediaType | None]:
    if arquivo is None:
        return None, None
    caminho = IMAGENS / arquivo
    if not caminho.is_file():
        raise SystemExit(f"imagem ausente: {caminho}")
    media = await media_service.save(session, caminho.read_bytes())
    return media.id, media.media_type


async def semear(campaign_id: int | None) -> None:
    async with SessionLocal() as session:
        if campaign_id is None:
            campanha = (
                await session.execute(
                    select(Campaign).where(
                        Campaign.tenant_id == settings.tenant_id,
                        Campaign.name == "Campanha de teste",
                    )
                )
            ).scalar_one_or_none()
            if campanha is None:
                raise SystemExit(
                    'nenhuma campanha chamada "Campanha de teste"; '
                    "informe --campaign-id"
                )
        else:
            campanha = await session.get(Campaign, campaign_id)
            if campanha is None or campanha.tenant_id != settings.tenant_id:
                raise SystemExit(f"campanha {campaign_id} nao existe neste tenant")

        # Compliance antes de qualquer escrita: um texto reprovado no meio do
        # seed deixaria a campanha metade nova, metade velha.
        for corpo, _ in ETAPAS.values():
            assert_compliant(corpo)
        for opcao in OPCOES:
            assert_compliant(opcao["label"])
            if opcao["response_body"]:
                assert_compliant(opcao["response_body"])

        # Idempotencia: o conteudo anterior desta campanha sai junto com a
        # midia que so ele referenciava.
        antigos = list(
            (
                await session.execute(
                    select(FunnelContent).where(
                        FunnelContent.tenant_id == settings.tenant_id,
                        FunnelContent.campaign_id == campanha.id,
                    )
                )
            ).scalars()
        )
        opcoes_antigas = list(
            (
                await session.execute(
                    select(QualificationOption).where(
                        QualificationOption.tenant_id == settings.tenant_id,
                        QualificationOption.campaign_id == campanha.id,
                    )
                )
            ).scalars()
        )
        for linha in antigos:
            if linha.media_id:
                await media_service.delete(session, linha.media_id)
            await session.delete(linha)
        for opcao in opcoes_antigas:
            if opcao.response_media_id:
                await media_service.delete(session, opcao.response_media_id)
            await session.delete(opcao)
        await session.flush()

        for step, (corpo, arquivo) in ETAPAS.items():
            media_id, media_type = await _midia(session, arquivo)
            session.add(
                FunnelContent(
                    tenant_id=settings.tenant_id,
                    campaign_id=campanha.id,
                    step=step,
                    body=corpo,
                    media_id=media_id,
                    media_type=media_type,
                )
            )

        for opcao in OPCOES:
            media_id, media_type = await _midia(session, opcao["media"])
            session.add(
                QualificationOption(
                    tenant_id=settings.tenant_id,
                    campaign_id=campanha.id,
                    key=opcao["key"],
                    label=opcao["label"],
                    target=opcao.get("target", OptionTarget.INFORMATION),
                    sort_order=opcao["sort_order"],
                    is_active=True,
                    response_body=opcao["response_body"],
                    response_media_id=media_id,
                    response_media_type=media_type,
                )
            )

        await session.commit()

        print(f"campanha #{campanha.id} ({campanha.name}) semeada")
        print(f"  {len(ETAPAS)} etapas do funil")
        print(f"  {len(OPCOES)} opcoes de qualificacao")
        informativas = [o for o in OPCOES if o.get("target") is None]
        print(f"  {len(informativas)} direcoes informativas antes do atendimento humano")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(semear(args.campaign_id))


if __name__ == "__main__":
    main()
