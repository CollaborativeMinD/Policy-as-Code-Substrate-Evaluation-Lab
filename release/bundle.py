"""Install the exact qualified source tree or replay its component witness."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


def verify(root):
    if (root / "tests/verify_console.py").is_file():
        command = [str(root / "tests/verify_console.py")]
        receipt = root / "verification/console-witness.json"
    else:
        command = ["-m", "console_app.verify"]
        receipt = root / "console-evidence/witness.json"
    subprocess.run([sys.executable, "-B", *command], cwd=root, check=True)
    result = json.loads(receipt.read_bytes())
    if result.get("status") != "PASS":
        raise ValueError("Missing component witness")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("destination", type=Path)
    witness = sub.add_parser("verify")
    witness.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    with ZipFile(Path(__file__).with_name("payload.zip")) as source:
        if args.operation == "unpack":
            args.destination.mkdir(parents=True, exist_ok=False)
            source.extractall(args.destination)
            return
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source.extractall(root)
            result = verify(root)
    if args.receipt:
        args.receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
