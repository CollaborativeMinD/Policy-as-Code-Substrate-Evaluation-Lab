"""Build and verify the source and image distributions of one Git revision."""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT, timeout=600):
    return subprocess.run(args, cwd=cwd, check=True, timeout=timeout, stdout=subprocess.PIPE).stdout


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def put(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf8")


@dataclass(frozen=True)
class Scan:
    scanner_version: str
    block_severities: list[str]


@dataclass(frozen=True)
class Release:
    version: int
    name: str
    release_version: str
    python_image: str
    uv_image: str
    python_apk: str
    platforms: list[str]
    uid: int
    gid: int
    tmpfs_mib: int
    process_limit: int
    build_seconds: int
    witness_seconds: int
    scan: Scan

    @classmethod
    def read(cls):
        doc = tomllib.loads((ROOT / "release/policy.toml").read_text(encoding="utf8"))
        policy = cls(**(doc | {"scan": Scan(**doc["scan"])}))
        if (type(policy.version) is not int or policy.version != 1
                or not re.fullmatch(r"pac-[a-z][a-z0-9-]+", policy.name)
                or not re.fullmatch(r"\d+\.\d+\.\d+", policy.release_version)
                or not re.fullmatch(r"cgr\.dev/chainguard/wolfi-base@sha256:[0-9a-f]{64}", policy.python_image)
                or not re.fullmatch(r"ghcr\.io/astral-sh/uv:[\w.]+@sha256:[0-9a-f]{64}", policy.uv_image)
                or not re.fullmatch(r"3\.13\.\d+_git\d+-r\d+", policy.python_apk)
                or sorted(policy.platforms) != ["linux/amd64", "linux/arm64"]
                or not re.fullmatch(r"\d+\.\d+\.\d+", policy.scan.scanner_version)
                or not set(policy.scan.block_severities) <= {"LOW","MEDIUM","HIGH","CRITICAL"}
                or "CRITICAL" not in policy.scan.block_severities):
            raise ValueError("Invalid release declaration")
        for value, low, high in [(policy.uid,1000,65534),(policy.gid,1000,65534),(policy.tmpfs_mib,64,2048),
                                 (policy.process_limit,32,512),(policy.build_seconds,60,3600),(policy.witness_seconds,30,1800)]:
            if type(value) is not int or not low <= value <= high:
                raise ValueError("Invalid release resource budget")
        return policy

    def compose(self, image, target, pin):
        args = ["serve", "--policy", "/app/console.toml", "--sha256", pin, "--credentials", "/state/credentials"]
        if (ROOT / "console_app/verify.py").exists():
            args += ["--state", "/state/ledger"]
        return {"services": {"console": {"image": image, "platform": target, "user": f"{self.uid}:{self.gid}",
                "read_only": True, "network_mode": "none", "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"], "pids_limit": self.process_limit,
                "tmpfs": [f"/tmp:rw,nosuid,nodev,size={self.tmpfs_mib}m"],
                "volumes": ["state:/state"], "command": args}}, "volumes": {"state": {}}}


def revision():
    sha1 = run("git","rev-parse","HEAD").decode().strip()
    if sha1 != os.environ.get("GITHUB_SHA",sha1) or not re.fullmatch("[0-9a-f]{40}", sha1):
        raise ValueError("Unexpected checkout")
    if run("git","status","--porcelain","--untracked-files=no"):
        raise ValueError("Modified tracked release inputs")
    return sha1


def archive(commit, dest):
    run("git", "archive", "--format=zip", "--output", str(dest), commit)


def package(cfg, commit, out):
    with TemporaryDirectory() as tmp:
        stage = Path(tmp)
        module = cfg.name.replace("-", "_") + "_release"
        pkg = stage / module
        pkg.mkdir()
        archive(commit, pkg / "payload.zip")
        shutil.copyfile(ROOT/"release/bundle.py", pkg/"__init__.py")
        shutil.copyfile(ROOT/"README.md", stage/"README.md")
        deps = [line.split(" \\")[0].strip() for line in (ROOT/"release/requirements.lock").read_text().splitlines()
                if re.match(r"^[a-zA-Z0-9][\w.-]*(\[.*?\])?==", line)]
        project = f"""[build-system]
requires = ["setuptools==80.9.0", "wheel==0.45.1"]
build-backend = "setuptools.build_meta"
[project]
name = "{cfg.name}-distribution"
version = "{cfg.release_version}+g{commit[:12]}"
requires-python = ">=3.13,<3.14"
description = "Qualified Policy-as-Code component distribution"
readme = "README.md"
dependencies = {json.dumps(deps)}
[project.scripts]
{cfg.name} = "{module}:main"
[tool.setuptools]
packages = ["{module}"]
[tool.setuptools.package-data]
{module} = ["payload.zip"]
"""
        (stage/"pyproject.toml").write_text(project,encoding="utf8")
        run(sys.executable,"-m","build","--no-isolation","--outdir",str(out),cwd=stage)
        shutil.copyfile(pkg/"payload.zip",out/(cfg.name+"-source.zip"))
        wheel, = out.glob("*.whl")
        with ZipFile(wheel) as z:
            if hashlib.sha256(z.read(module+"/payload.zip")).hexdigest()!=sha(pkg/"payload.zip"):
                raise ValueError("Wheel lost source identity")
        run(sys.executable,"-m","venv","--without-pip", str(stage/"installed"))
        python=stage/"installed"/("Scripts/python.exe" if os.name=="nt" else "bin/python")
        run(sys.executable,"-m","pip","--python",str(python),"install","--no-index","--no-deps",str(wheel))
        run(str(python),"-I","-c",f"import sys;import {module};sys.argv=['unpack','unpack',sys.argv[1]];{module}.main()",str(stage/"expanded"),cwd=stage)
        if sha(stage/"expanded/console.toml") != hashlib.sha256(run("git","show",commit+":console.toml")).hexdigest():
            raise ValueError("Installed policy bytes differ from the revision")
        put(out/"package-receipt.json",{"commit":commit,"system":sys.platform,"package_sha256":{p.name:sha(p) for p in out.iterdir() if p.is_file()}})


def scan(cfg, image, destination, scanner):
    version = run(scanner,"--version").decode()
    if f"Version: {cfg.scan.scanner_version}\n" not in version.replace("\r\n","\n"):
        raise ValueError("Unexpected scanner version")
    run(scanner,"image","--quiet","--scanners","vuln,secret","--image-src","docker","--format","json",
        "--output",str(destination),image,timeout=cfg.build_seconds)
    doc=json.loads(destination.read_bytes())
    if not doc.get("Metadata",{}).get("OS") or not doc.get("Results"):
        raise ValueError("Scan returned no OS or component inventory")
    blocked = [(r["Target"],v["VulnerabilityID"]) for r in doc["Results"]
               for v in r.get("Vulnerabilities",[]) if v["Severity"] in cfg.scan.block_severities]
    if blocked or any(r.get("Secrets") for r in doc["Results"]):
        raise ValueError(f"Image scan denied promotion: {blocked[:12]}. Review the scan report.")
    return sha(destination)


def container(cfg, commit, out, platform, scanner):
    if platform not in cfg.platforms:
        raise ValueError("Unadmitted platform")
    arch=platform.split("/")[1]
    tag=f"{cfg.name}:{commit[:12]}-{arch}"
    with TemporaryDirectory() as tmp:
        context=Path(tmp)
        archive(commit,context/"payload.zip")
        shutil.copyfile(ROOT/"release/requirements.lock",context/"requirements.lock")
        shutil.copyfile(ROOT/"release/Dockerfile",context/"Dockerfile")
        args={"BASE":cfg.python_image,"UV":cfg.uv_image,"PYTHON_APK":cfg.python_apk,"REVISION":commit,
              "RUNTIME_UID":cfg.uid,"RUNTIME_GID":cfg.gid}
        command=["docker","buildx","build","--platform",platform,"--load","--tag",tag]
        for key,value in args.items():command.extend(["--build-arg",f"{key}={value}"])
        run(*command,str(context),timeout=cfg.build_seconds)
    image,=json.loads(run("docker","image","inspect",tag))
    if image["Os"]+"/"+image["Architecture"]!=platform or image["Config"]["Labels"]["org.opencontainers.image.revision"]!=commit:
        raise ValueError("Image platform or origin mismatch")
    report=scan(cfg,tag,out/"scan.json",scanner)
    spec=out/"compose.json"
    pin=hashlib.sha256(run("git","show",commit+":console.toml")).hexdigest()
    put(spec,cfg.compose(tag,platform,pin))
    project=cfg.name+"-"+os.urandom(4).hex()
    compose=["docker","compose","-p",project,"-f",str(spec)]
    try:
        run(*compose,"config","--quiet")
        probe="""import json,os,platform,sys,tempfile,shutil
from pathlib import Path
from release.bundle import verify
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)/"app"
    shutil.copytree("/app",root)
    result=verify(root)
print(json.dumps(dict(status=result["status"], witness=result, uid=os.getuid(), gid=os.getgid(), machine=platform.machine())))
"""
        raw=run(*compose,"run","--rm","-T","--entrypoint","python3.13","console","-B","-c",probe,timeout=cfg.witness_seconds)
        witness=json.loads(raw.splitlines()[-1])
        if (witness["status"],witness["uid"],witness["gid"],witness["machine"]) != (
                "PASS",cfg.uid,cfg.gid,{"amd64":"x86_64","arm64":"aarch64"}[arch]):
            raise ValueError("Compose identity or effect mismatch")
    finally:
        run(*compose,"down","--volumes","--remove-orphans")
    dest=out/(cfg.name+"-"+arch+".image.tar.gz")
    with TemporaryDirectory() as temp:
        raw=Path(temp)/"image.tar"
        run("docker","image","save","-o",str(raw),tag,timeout=cfg.build_seconds)
        with raw.open("rb") as source,dest.open("wb") as sink,gzip.GzipFile(fileobj=sink,mode="wb",mtime=0,compresslevel=3) as packed:
            shutil.copyfileobj(source,packed)
    run("docker","image","load","--input",str(dest),timeout=cfg.build_seconds)
    if json.loads(run("docker","image","inspect",tag))[0]["Id"]!=image["Id"]:
        raise ValueError("Restored image identity differs")
    put(out/"verification.json",dict(commit=commit,platform=platform,image=tag,image_id=image["Id"],
        policy_sha256=pin, release_policy_sha256=sha(ROOT/"release/policy.toml"),scan_sha256=report,
        distribution_sha256=sha(dest),compose_sha256=sha(spec),effect=witness))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("package","container"))
    parser.add_argument("output",type=Path)
    parser.add_argument("--platform")
    parser.add_argument("--scanner",default="trivy")
    args=parser.parse_args()
    policy=Release.read()
    commit=revision()
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    if args.action=="package":package(policy,commit,output)
    else:container(policy,commit,output,args.platform,args.scanner)
