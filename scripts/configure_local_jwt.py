#!/usr/bin/env python3
"""Generate a persistent JWT signing key on each independent development server."""
import argparse
import os
from pathlib import Path
import re
import secrets
import tempfile


def configure(path: Path, rotate: bool = False) -> bool:
    text = path.read_text()
    pattern = r"(?m)^JWT_SIGNING_KEY\s*=.*$"
    existing = re.search(pattern, text)
    if existing and not rotate:
        print("JWT_SIGNING_KEY already configured; unchanged. Use --rotate only to invalidate existing sessions.")
        return False
    line = "JWT_SIGNING_KEY=" + secrets.token_urlsafe(48)
    updated = re.sub(pattern, lambda _: line, text) if existing else text.rstrip() + "\n" + line + "\n"
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".jwt-env-")
    try:
        with os.fdopen(fd, "w") as output:
            output.write(updated)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Independent JWT key saved (not printed). Restart backend to apply. Do not copy this .env to another server.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    parser.add_argument("--rotate", action="store_true")
    args = parser.parse_args()
    configure(args.env, args.rotate)
