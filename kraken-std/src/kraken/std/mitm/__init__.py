"""
Manages a `mitmweb` instance to run in the background for injecting basic-auth into requests to hosts for which
credentials are passed down. The `mitmweb` web interface can be reached on `localhost:8900` while it is running.
The proxy stays alive as a daemon process until its configuration changes.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Mapping

from kraken.std.util.daemon_controller import DaemonController

logger = logging.getLogger(__name__)

daemon_state_file = Path("~/.config/krakenw/.mitmweb-daemon-state.json").expanduser()
daemon_log_file = daemon_state_file.with_suffix(".log")
mitmweb_port = 8899
mitmweb_ui_port = 8900
mitmproxy_ca_cert_file = Path("~/.mitmproxy/mitmproxy-ca-cert.pem").expanduser()
inject_auth_addon_file = Path(__file__).parent / "mitm_addon.py"


def start_mitmweb_proxy(auth: Mapping[str, tuple[str, str]], startup_wait_time: float = 3.0) -> tuple[str, Path]:
    controller = DaemonController("kraken.mitmweb", daemon_state_file)
    started = controller.run(
        command=[
            "mitmweb",
            "--no-web-open-browser",
            "--web-port",
            str(mitmweb_ui_port),
            "--listen-port",
            str(mitmweb_port),
            "-s",
            str(inject_auth_addon_file),
            "--set",
            "auth=" + json.dumps(auth),
            "--ssl-insecure",
        ],
        cwd=Path("~").expanduser(),
        stdout=daemon_log_file,
        stderr="stdout",
    )
    if started:
        # Give the proxy some time to fully start up.
        time.sleep(startup_wait_time)
        if not controller.is_alive():
            raise RuntimeError("The mitmweb proxy failed to start. Check its logs at %s" % daemon_log_file)
    return f"localhost:{mitmweb_port}", mitmproxy_ca_cert_file


def stop_mitmweb_proxy() -> None:
    controller = DaemonController("kraken.mitmweb", daemon_state_file)
    controller.stop()
