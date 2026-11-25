"""Read the live inventory through a newly provisioned distribution's viewer role."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import time
import tomllib

from console_app.client import Remote


def main():
    config = tomllib.loads(Path("/app/console.toml").read_text())
    deadline = time.monotonic() + int(sys.argv[1])
    while True:
        try:
            with socket.create_connection((config["host"], config["port"]), timeout=1):
                break
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError("The shipped entry point did not become ready")
            time.sleep(0.2)
    remote = Remote(config["port"], Path("/state/credentials/viewer.token"))
    reply = asyncio.run(remote.call("inventory.read"))
    if reply["role"] != "viewer" or not reply["rows"]:
        raise ValueError("The shipped service returned no viewer inventory")
    print(json.dumps({"role": reply["role"], "inventory_rows": len(reply["rows"])}))


if __name__ == "__main__":
    main()
