from contextlib import contextmanager
from hashlib import sha256
from secrets import token_urlsafe
import socket
import subprocess
import sys
import time
from lab import transact

@contextmanager
def setup(tmp, root, config):
    state = tmp / "lab.sqlite"
    for name in ("pi-thermal", "pi-loop-budget"):
        path = root / "policies" / (name + ".toml")
        transact("admit", path, state, sha256(path.read_bytes()).hexdigest())
    keys = tmp / "native-keys"
    keys.mkdir()
    for role in ("reader","evaluator"):
        (keys/(role+".token")).write_text(token_urlsafe(40))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port = sock.getsockname()[1]
    policy = tmp / "native.toml"
    policy.write_text((root/"mcp-policy.toml").read_text().replace("port = 8765",f"port = {port}"))
    proc = subprocess.Popen([sys.executable, str(root/"lab_mcp.py"),"--policy",str(policy),
                             "--sha256",sha256(policy.read_bytes()).hexdigest(),"--state",str(state),
                             "--credentials",str(keys)])
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.1):
                    break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError("Lab MCP exited")
                time.sleep(.05)
        upstream = tmp / "upstream.toml"
        upstream.write_text(f'port = {port}\nreader_file = "native-keys/reader.token"\nevaluator_file = "native-keys/evaluator.token"\n')
        yield config.replace(".local/lab-upstream.toml",upstream.as_posix())
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def check(effect):
    assert effect["disposition"] and len(effect["receipt_sha256"]) == 64
