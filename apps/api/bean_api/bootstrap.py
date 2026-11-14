"""Initialize local authentication without emitting bearer credentials."""

import json
import os
from pathlib import Path
import secrets


def main() -> None:
    target = Path(os.getenv("BEAN_AUTH_FILE", "var/auth.json"))
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"Existing local authentication preserved: {target.resolve()}")
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump({"local-researcher": secrets.token_urlsafe(48)}, stream)
        stream.write("\n")
    print(f"Created local authentication: {target.resolve()}")
    print("Read this private file locally to authorize API requests. Do not commit or share it.")


if __name__ == "__main__":
    main()
