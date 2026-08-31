"""Midia do funil e do atendimento, guardada no PostgreSQL.

Imagem, video e audio entram como linha em `media_objects` — bytes inclusive.
Nada e gravado em disco: o processo nao tem volume de midia, e nenhum arquivo
sobrevive a um restart do container.

O motivo e de operacao, nao de gosto: com o arquivo fora do banco, o backup
do PostgreSQL restaurava a conversa sem os anexos, apontando para um caminho
que nao existe mais — e sem erro nenhum no caminho. Agora `pg_dump` leva
tudo, e o par (mensagem, anexo) entra e sai na mesma transacao.

O bot le os bytes daqui e manda ao Telegram como upload (`BufferedInputFile`);
uma URL local nunca serviu, porque o servidor do Telegram nao alcanca o host.
"""

import asyncio
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import MediaType
from app.core.logging import get_logger
from app.models import MediaObject

logger = get_logger(__name__)


class MediaError(ValueError):
    pass


#: Assinatura -> (tipo, extensao). A validacao e por conteudo, nunca pela
#: extensao enviada pelo cliente: renomear um .exe para .jpg nao passa aqui.
SIGNATURES: list[tuple[bytes, int, MediaType, str]] = [
    (b"\xff\xd8\xff", 0, MediaType.PHOTO, ".jpg"),
    (b"\x89PNG\r\n\x1a\n", 0, MediaType.PHOTO, ".png"),
    (b"GIF87a", 0, MediaType.PHOTO, ".gif"),
    (b"GIF89a", 0, MediaType.PHOTO, ".gif"),
    (b"RIFF", 0, MediaType.PHOTO, ".webp"),  # confirmado por WEBP no offset 8
    (b"ftyp", 4, MediaType.VIDEO, ".mp4"),  # brand no offset 8 separa M4A de MP4
    (b"\x1aE\xdf\xa3", 0, MediaType.VIDEO, ".webm"),
    (b"OggS", 0, MediaType.VOICE, ".ogg"),  # sem OpusHead vira AUDIO
    (b"ID3", 0, MediaType.AUDIO, ".mp3"),
    (b"\xff\xfb", 0, MediaType.AUDIO, ".mp3"),
    (b"\xff\xf3", 0, MediaType.AUDIO, ".mp3"),
    (b"\xff\xf2", 0, MediaType.AUDIO, ".mp3"),
]

#: Brands do container ISO-BMFF que indicam audio. O mesmo `ftyp` no offset 4
#: serve MP4 e M4A: sem olhar o brand, todo M4A entraria como video e sairia
#: pelo `send_video`.
AUDIO_BRANDS = {b"M4A ", b"M4B ", b"M4P "}

#: Extensao -> Content-Type gravado no registro.
CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}

#: Tempo maximo de conversao de um audio gravado. Voz de atendimento tem
#: segundos; passar disso e sinal de arquivo estranho, nao de fila.
TRANSCODE_TIMEOUT_SECONDS = 60


def detect(content: bytes) -> tuple[MediaType, str]:
    """Identifica o tipo pelo conteudo. Lanca MediaError se nao for suportado."""
    for magic, offset, media_type, ext in SIGNATURES:
        if content[offset : offset + len(magic)] != magic:
            continue
        if ext == ".webp" and content[8:12] != b"WEBP":
            continue
        if ext == ".mp4" and content[8:12] in AUDIO_BRANDS:
            return MediaType.AUDIO, ".m4a"
        if ext == ".ogg" and b"OpusHead" not in content[:1024]:
            # Ogg que nao e Opus (Vorbis, FLAC) nao serve como mensagem de voz
            # do Telegram; vai como arquivo de audio.
            return MediaType.AUDIO, ".ogg"
        return media_type, ext
    raise MediaError(
        "formato nao suportado. Envie imagem (JPG, PNG, GIF, WEBP), "
        "video (MP4, WEBM) ou audio (OGG, MP3, M4A)."
    )


def content_type_for(extension: str) -> str:
    return CONTENT_TYPES.get(extension.lower(), "application/octet-stream")


async def save(session: AsyncSession, content: bytes) -> MediaObject:
    """Grava a midia e devolve a linha, ja com id.

    Nao faz commit: quem chama decide a transacao, e e isso que garante que
    anexo e mensagem entrem juntos ou nao entrem.
    """
    limit = settings.max_media_mb * 1024 * 1024
    if len(content) > limit:
        raise MediaError(f"arquivo maior que o limite de {settings.max_media_mb}MB")
    if not content:
        raise MediaError("arquivo vazio")

    media_type, extension = detect(content)
    media = MediaObject(
        tenant_id=settings.tenant_id,
        media_type=media_type,
        content_type=content_type_for(extension),
        extension=extension,
        size_bytes=len(content),
        content=content,
    )
    session.add(media)
    await session.flush()

    logger.info(
        "midia armazenada",
        extra={
            "event": "MEDIA_SAVED",
            "media_id": media.id,
            "type": media_type.value,
            "bytes": len(content),
        },
    )
    return media


async def load(session: AsyncSession, media_id: int) -> MediaObject | None:
    """Le a midia deste tenant. Id de outro tenant devolve None, nao a linha."""
    stmt = select(MediaObject).where(
        MediaObject.id == media_id,
        MediaObject.tenant_id == settings.tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete(session: AsyncSession, media_id: int) -> bool:
    """Remove a midia. Devolve False quando ela nao existe neste tenant."""
    media = await load(session, media_id)
    if media is None:
        return False
    await session.delete(media)
    return True


async def transcode_voice(content: bytes) -> bytes:
    """Converte uma gravacao do navegador em OGG/Opus.

    O MediaRecorder entrega WebM/Opus no Chrome e MP4/AAC no Safari; o
    `sendVoice` do Telegram so aceita OGG/Opus. Recodificar aqui e o que
    permite gravar direto no painel sem depender do formato do navegador —
    por isso o `ffmpeg` faz parte da imagem.

    O arquivo temporario e do ffmpeg, nao armazenamento: `pipe:` nao serve
    para MP4 do Safari, cujo indice fica no fim e exige seek. Ele vive dentro
    do `TemporaryDirectory` e some ao fim da chamada; o que persiste vai para
    o banco.

    Mono a 32kbps: e voz, e o limite de 20MB do Telegram passa a ser
    inalcancavel na pratica.
    """
    if not content:
        raise MediaError("audio vazio")
    limit = settings.max_media_mb * 1024 * 1024
    if len(content) > limit:
        raise MediaError(f"arquivo maior que o limite de {settings.max_media_mb}MB")

    with tempfile.TemporaryDirectory() as workdir:
        source = Path(workdir) / "gravacao"
        target = Path(workdir) / "voz.ogg"
        source.write_bytes(content)

        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            "-ar",
            "48000",
            "-ac",
            "1",
            str(target),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, erro = await asyncio.wait_for(
                process.communicate(), timeout=TRANSCODE_TIMEOUT_SECONDS
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise MediaError("conversao do audio demorou demais") from None

        if process.returncode != 0 or not target.is_file():
            logger.warning(
                "falha ao converter audio gravado",
                extra={
                    "event": "VOICE_TRANSCODE_FAILED",
                    "returncode": process.returncode,
                    "stderr": erro.decode("utf-8", "replace")[:300],
                },
            )
            raise MediaError("nao foi possivel converter o audio gravado")

        return target.read_bytes()
