"""Module to run app in console."""
import os
import socket
import stat
from typing import Dict

import uvicorn

from dataset.config import settings


def listen_url_to_config(listen: str) -> Dict:
    """Convert listen url string into app config."""
    input_val = listen or ""
    schema: str = input_val[:4]
    listen_value: str = input_val[7:]

    if schema == "unix":  # noqa: R505
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            if os.path.exists(listen_value):
                os.remove(listen_value)
            sock.bind(listen_value)
            os.chmod(listen_value, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except socket.error as msg:
            raise RuntimeError(f"Failed to create socket: {msg}") from msg

        return {"sock": sock}
    elif schema == "http":
        host, port = listen_value.split(":")

        if not port:
            port = 8080

        return {"host": host, "port": int(port)}
    return {"host": "0.0.0.0", "port": 8080}


def main() -> None:
    """Launch dataset."""
    params = listen_url_to_config(settings.GS_LISTEN)
    params["reload"] = settings.GS_ENVIRONMENT in ("dev", "test")
    uvicorn.run("dataset.app:application", **params)


if __name__ == "__main__":
    main()
