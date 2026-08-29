"""Armazenamento de midia do funil.

Arquivo enviado pelo painel fica num volume local e e lido pelo bot na hora
de mandar a mensagem. Nunca e servido por HTTP nem exposto por URL publica:
o Telegram recebe os bytes, e a URL de um servidor local nao seria alcancavel
por ele de qualquer forma.
"""

import secrets
from pathlib import Path

from app.core.config import settings
from app.core.enums import MediaType
from app.core.logging import get_logger

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
    (b"ftyp", 4, MediaType.VIDEO, ".mp4"),
    (b"\x1aE\xdf\xa3", 0, MediaType.VIDEO, ".webm"),
]


def detect(content: bytes) -> tuple[MediaType, str]:
    """Identifica o tipo pelo conteudo. Lanca MediaError se nao for suportado."""
    for magic, offset, media_type, ext in SIGNATURES:
        if content[offset : offset + len(magic)] == magic:
            if ext == ".webp" and content[8:12] != b"WEBP":
                continue
            return media_type, ext
    raise MediaError(
        "formato nao suportado. Envie imagem (JPG, PNG, GIF, WEBP) "
        "ou video (MP4, WEBM)."
    )


def media_root() -> Path:
    root = Path(settings.media_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save(content: bytes) -> tuple[str, MediaType, int]:
    """Grava o arquivo e devolve (caminho_relativo, tipo, bytes)."""
    limit = settings.max_media_mb * 1024 * 1024
    if len(content) > limit:
        raise MediaError(f"arquivo maior que o limite de {settings.max_media_mb}MB")
    if not content:
        raise MediaError("arquivo vazio")

    media_type, ext = detect(content)

    # Nome gerado por nos: nome vindo do cliente permitiria path traversal e
    # sobrescrita de arquivo existente.
    name = f"{secrets.token_hex(16)}{ext}"
    relative = f"{settings.tenant_id}/{name}"

    destination = media_root() / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)

    logger.info(
        "midia armazenada",
        extra={"event": "MEDIA_SAVED", "type": media_type.value, "bytes": len(content)},
    )
    return relative, media_type, len(content)


def delete(relative_path: str) -> None:
    """Remove um arquivo do volume, ignorando caminho fora da raiz."""
    root = media_root().resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        logger.warning(
            "tentativa de remover midia fora da raiz",
            extra={"event": "MEDIA_PATH_REJECTED"},
        )
        return
    target.unlink(missing_ok=True)
