"""Midia do atendimento: deteccao de formato, upload e leitura pelo painel.

O que se garante aqui e o que quebraria em silencio: audio entrando como
video por causa do `ftyp`, o clipe do chat barrado pela permissao errada, e a
rota de midia servindo anexo de outra conversa ou de outro tenant.

Os bytes vivem em `media_objects` — nenhum teste toca o sistema de arquivos,
porque o codigo de runtime tambem nao toca.
"""

import asyncio
import shutil

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import MediaType, MessageDirection, OperatorRole, SenderType
from app.core.security import create_access_token
from app.models import Conversation, MediaObject, Message, Operator, TelegramUser
from app.services import media_service
from app.services.auth_service import create_operator

SENHA = "senha-de-teste-1234"

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64
M4A = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 64
OGG_OPUS = b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 32
OGG_VORBIS = b"OggS" + b"\x00" * 24 + b"\x01vorbis" + b"\x00" * 32
MP3 = b"ID3\x03\x00\x00\x00" + b"\x00" * 64


@pytest.fixture
def client(session: AsyncSession):
    from app.core.database import get_session
    from app.main import app

    async def _session_override():
        yield session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    yield httpx.AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.clear()


def _auth(operator: Operator) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(operator.id, operator.role.value)}"}


async def _conversa(session: AsyncSession, telegram_id: int = 9001) -> Conversation:
    user = TelegramUser(tenant_id=settings.tenant_id, telegram_id=telegram_id)
    session.add(user)
    await session.flush()
    conversation = Conversation(tenant_id=settings.tenant_id, telegram_user_id=user.id)
    session.add(conversation)
    await session.flush()
    return conversation


async def _mensagem_com_anexo(
    session: AsyncSession, conversation: Conversation, conteudo: bytes, tenant: str | None = None
) -> Message:
    midia = await media_service.save(session, conteudo)
    if tenant:
        midia.tenant_id = tenant
    message = Message(
        tenant_id=tenant or settings.tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        sender_type=SenderType.USER,
        message_type=midia.media_type.value,
        content=None,
        media_id=midia.id,
        media_type=midia.media_type,
    )
    session.add(message)
    await session.flush()
    return message


# ------------------------------------------------------------------ deteccao
@pytest.mark.parametrize(
    ("conteudo", "esperado", "extensao"),
    [
        (JPEG, MediaType.PHOTO, ".jpg"),
        (MP4, MediaType.VIDEO, ".mp4"),
        (M4A, MediaType.AUDIO, ".m4a"),
        (OGG_OPUS, MediaType.VOICE, ".ogg"),
        (OGG_VORBIS, MediaType.AUDIO, ".ogg"),
        (MP3, MediaType.AUDIO, ".mp3"),
    ],
)
def test_deteccao_por_conteudo(conteudo: bytes, esperado: MediaType, extensao: str):
    """M4A e MP4 compartilham o `ftyp`; so o brand do offset 8 os separa."""
    assert media_service.detect(conteudo) == (esperado, extensao)


def test_formato_nao_suportado_e_recusado():
    with pytest.raises(media_service.MediaError):
        media_service.detect(b"%PDF-1.7 nao e midia")


async def test_midia_de_outro_tenant_nao_e_lida(session: AsyncSession):
    """`load` filtra por tenant: id de outra empresa nao devolve a linha."""
    midia = await media_service.save(session, JPEG)
    midia.tenant_id = "outra-empresa"
    await session.flush()

    assert await media_service.load(session, midia.id) is None
    assert await media_service.delete(session, midia.id) is False


# -------------------------------------------------------------------- upload
async def test_operador_anexa_no_chat(session: AsyncSession, client: httpx.AsyncClient):
    """A rota do chat existe porque `/content/media` exige `campaigns:write`.

    O mesmo operador que atende recebe 201 aqui e 403 la — se um dia as duas
    respostas ficarem iguais, ou a permissao mudou de lugar ou o clipe do chat
    voltou a ser inutil para quem usa o chat.
    """
    operator = await create_operator(
        session, email="op@teste.com", password=SENHA, role=OperatorRole.OPERATOR
    )
    conversation = await _conversa(session)
    await session.flush()

    async with client:
        no_chat = await client.post(
            f"/api/v1/conversations/{conversation.id}/media",
            files={"file": ("foto.jpg", JPEG, "image/jpeg")},
            headers=_auth(operator),
        )
        no_funil = await client.post(
            "/api/v1/content/media",
            files={"file": ("foto.jpg", JPEG, "image/jpeg")},
            headers=_auth(operator),
        )

    assert no_chat.status_code == 201
    assert no_chat.json()["media_type"] == "photo"
    assert no_funil.status_code == 403

    gravada = await session.get(MediaObject, no_chat.json()["media_id"])
    assert gravada is not None and gravada.content == JPEG, "bytes no banco"


async def test_upload_em_conversa_inexistente_responde_404(
    session: AsyncSession, client: httpx.AsyncClient
):
    operator = await create_operator(
        session, email="op404@teste.com", password=SENHA, role=OperatorRole.OPERATOR
    )
    await session.flush()

    async with client:
        response = await client.post(
            "/api/v1/conversations/99999/media",
            files={"file": ("foto.jpg", JPEG, "image/jpeg")},
            headers=_auth(operator),
        )

    assert response.status_code == 404


# --------------------------------------------------------------- leitura web
async def test_painel_le_o_anexo_da_mensagem(session: AsyncSession, client: httpx.AsyncClient):
    operator = await create_operator(
        session, email="leitura@teste.com", password=SENHA, role=OperatorRole.OPERATOR
    )
    conversation = await _conversa(session)
    message = await _mensagem_com_anexo(session, conversation, JPEG)

    async with client:
        response = await client.get(
            f"/api/v1/conversations/{conversation.id}/messages/{message.id}/media",
            headers=_auth(operator),
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == JPEG


async def test_anexo_de_outra_conversa_nao_e_servido(
    session: AsyncSession, client: httpx.AsyncClient
):
    """O par (conversa, mensagem) precisa bater: id de mensagem sozinho nao basta."""
    operator = await create_operator(
        session, email="cruzado@teste.com", password=SENHA, role=OperatorRole.OPERATOR
    )
    conversation = await _conversa(session, telegram_id=9002)
    outra = await _conversa(session, telegram_id=9003)
    message = await _mensagem_com_anexo(session, conversation, JPEG)

    async with client:
        response = await client.get(
            f"/api/v1/conversations/{outra.id}/messages/{message.id}/media",
            headers=_auth(operator),
        )

    assert response.status_code == 404


async def test_anexo_de_outro_tenant_nao_e_servido(
    session: AsyncSession, client: httpx.AsyncClient
):
    operator = await create_operator(
        session, email="tenant@teste.com", password=SENHA, role=OperatorRole.OPERATOR
    )
    conversation = await _conversa(session, telegram_id=9004)
    message = await _mensagem_com_anexo(session, conversation, JPEG, tenant="outra-empresa")

    async with client:
        response = await client.get(
            f"/api/v1/conversations/{conversation.id}/messages/{message.id}/media",
            headers=_auth(operator),
        )

    assert response.status_code == 404


async def test_anexo_exige_autenticacao(session: AsyncSession, client: httpx.AsyncClient):
    conversation = await _conversa(session, telegram_id=9005)
    message = await _mensagem_com_anexo(session, conversation, JPEG)

    async with client:
        response = await client.get(
            f"/api/v1/conversations/{conversation.id}/messages/{message.id}/media"
        )

    assert response.status_code == 401


# ---------------------------------------------------------- gravacao de voz
def _tem_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


@pytest.mark.skipif(not _tem_ffmpeg(), reason="ffmpeg nao instalado neste ambiente")
async def test_gravacao_do_navegador_vira_ogg_opus(tmp_path):
    """WebM/Opus (Chrome) precisa virar OGG/Opus para existir como voz.

    O teste gera a gravacao com o proprio ffmpeg em vez de carregar um
    binario fixo: assim o que se valida e a conversao, nao um arquivo de
    apoio que ninguem sabe reproduzir.
    """
    origem = tmp_path / "gravacao.webm"
    processo = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=1",
        "-c:a",
        "libopus",
        str(origem),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await processo.communicate()
    assert origem.is_file(), "ffmpeg sem libopus neste ambiente"

    convertido = await media_service.transcode_voice(origem.read_bytes())

    assert media_service.detect(convertido) == (MediaType.VOICE, ".ogg")


@pytest.mark.skipif(not _tem_ffmpeg(), reason="ffmpeg nao instalado neste ambiente")
async def test_arquivo_que_nao_e_audio_falha_com_erro_de_midia():
    with pytest.raises(media_service.MediaError):
        await media_service.transcode_voice(b"isto nao e audio nenhum")


# ------------------------------------------------------------------ descarte
async def test_anexo_nao_enviado_e_removido(
    session: AsyncSession, client: httpx.AsyncClient
):
    """Anexo que subiu e nao virou mensagem sai do banco ao ser descartado."""
    operator = await create_operator(
        session, email="descarte@teste.com", password=SENHA, role=OperatorRole.OPERATOR
    )
    conversation = await _conversa(session, telegram_id=9006)
    await session.flush()

    async with client:
        enviado = await client.post(
            f"/api/v1/conversations/{conversation.id}/media",
            files={"file": ("foto.jpg", JPEG, "image/jpeg")},
            headers=_auth(operator),
        )
        media_id = enviado.json()["media_id"]
        assert await session.get(MediaObject, media_id) is not None

        response = await client.request(
            "DELETE",
            f"/api/v1/conversations/{conversation.id}/media",
            params={"media_id": media_id},
            headers=_auth(operator),
        )

    assert response.status_code == 204
    assert await media_service.load(session, media_id) is None


async def test_anexo_ja_enviado_nao_e_removido(
    session: AsyncSession, client: httpx.AsyncClient
):
    """Apagar o arquivo de uma mensagem entregue deixaria buraco no historico."""
    operator = await create_operator(
        session, email="emuso@teste.com", password=SENHA, role=OperatorRole.OPERATOR
    )
    conversation = await _conversa(session, telegram_id=9007)
    message = await _mensagem_com_anexo(session, conversation, JPEG)

    async with client:
        response = await client.request(
            "DELETE",
            f"/api/v1/conversations/{conversation.id}/media",
            params={"media_id": message.media_id},
            headers=_auth(operator),
        )

    assert response.status_code == 409
    assert await media_service.load(session, message.media_id) is not None


async def test_descarte_de_midia_de_outro_tenant_nao_apaga_nada(
    session: AsyncSession, client: httpx.AsyncClient
):
    operator = await create_operator(
        session, email="fora@teste.com", password=SENHA, role=OperatorRole.OPERATOR
    )
    conversation = await _conversa(session, telegram_id=9008)
    alheia = await media_service.save(session, JPEG)
    alheia.tenant_id = "outra-empresa"
    await session.flush()

    async with client:
        response = await client.request(
            "DELETE",
            f"/api/v1/conversations/{conversation.id}/media",
            params={"media_id": alheia.id},
            headers=_auth(operator),
        )

    assert response.status_code == 404
    assert await session.get(MediaObject, alheia.id) is not None
