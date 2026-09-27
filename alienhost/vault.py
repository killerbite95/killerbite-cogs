"""
Cifrado en reposo de las claves API de Pelican.

Las claves se guardan en la Config de Red cifradas con Fernet (AES-128-CBC +
HMAC). La clave maestra vive en un archivo aparte dentro de la carpeta de
datos del cog (permisos 600), de modo que un volcado de la configuracion de
Red no expone las claves de los usuarios.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class Vault:
    def __init__(self, path: Path):
        self.path = path
        self._fernet: Optional[Fernet] = None

    def _load(self) -> Fernet:
        if self._fernet is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                key = self.path.read_bytes().strip()
            else:
                key = Fernet.generate_key()
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as fp:
                    fp.write(key)
            self._fernet = Fernet(key)
        return self._fernet

    def encrypt(self, value: str) -> str:
        return self._load().encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, token: Optional[str]) -> Optional[str]:
        if not token:
            return None
        try:
            return self._load().decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            return None
