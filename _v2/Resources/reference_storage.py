"""Isolate frozen and recovered replay versions without changing source archives."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import ast
import json
import sys
import tempfile
import zipfile
from .contracts import ContractError

ROOT=Path(__file__).resolve().parent


def restore_optional_report_fields(path):
    text=path.read_text();lines=text.splitlines(keepends=True)
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.ClassDef) and n.name=='SubstrateWoundReport')
    names={'energy_viability','precision_viability','return_authority_remaining_s',
           'task_class_integrity','lawful_grounding_bias'}
    for field in node.body:
        if isinstance(field,ast.AnnAssign) and field.target.id in names:
            assert ast.unparse(field.annotation)=='float' and field.value is None
            lines[field.lineno-1]=f'    {field.target.id}: float | None = None\n'
    path.write_text(''.join(lines))


def reference_root(version='bundle'):
    return _reference_root(version)


@lru_cache(maxsize=2)
def _reference_root(version):
    if version not in ('bundle','recovered'):
        raise ContractError('reference version must be bundle or recovered')
    archive=ROOT/'evidence/Legacy_Substrate_Reference.zip'
    expected=(ROOT/'evidence/legacy_archive.sha256').read_text().strip()
    if sha256(archive.read_bytes()).hexdigest()!=expected:
        raise ContractError('frozen archive hash mismatch')
    temp=tempfile.TemporaryDirectory(prefix='hmt-substrate-reference-')
    base=Path(temp.name);namespace='hmt_substrate_'+version
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if not (base/info.filename).resolve().is_relative_to(base):
                raise ContractError('unsafe archive member')
        z.extractall(base)
    package=base/namespace;(base/'substrate_profiles_registry').rename(package)
    if version=='recovered':
        install_recovery(package)
    if namespace in sys.modules:
        raise ContractError('competing reference package already imported; restart process')
    sys.path.insert(0,str(base))
    return temp,base,namespace


def install_recovery(package):
    manifest=json.loads((ROOT/'evidence/recovered_manifest.json').read_text())
    archive=ROOT/'evidence/Recovered_Research.zip'
    with zipfile.ZipFile(archive) as z:
        for record in manifest['files']:
            raw=z.read(record['name'])
            if sha256(raw).hexdigest()!=record['sha256']:
                raise ContractError('recovered source hash mismatch')
            if record['install']:
                (package/'admission'/record['name']).write_bytes(raw)
    restore_optional_report_fields(package/'profiles/platform_profile_primitive.py')
