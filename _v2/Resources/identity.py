"""Bind a configuration to executable laws as well as its catalog data."""
from hashlib import sha256
from pathlib import Path

FILES = ('__init__.py','contracts.py','identity.py','registry.py','wounds.py',
         'evaluate.py','mechanics.py','fields.py','response.py','replay.py','reference_storage.py')


def implementation_hash():
    root=Path(__file__).resolve().parent
    digest=sha256()
    for name in FILES:
        digest.update(name.encode()+b'\0')
        digest.update((root/name).read_bytes())
    return digest.hexdigest()
