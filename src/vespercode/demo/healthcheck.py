"""T30.2 legacy step 30.B: the public Demo health boundary.

``main()`` is the explicit capability-absence verification of the headless
Demo (card 30.B Goal): it reads the platform-injected ``PORT`` (SPEC
§8.3), builds the closed Demo app with the validated port, and verifies
that the capability registry is exactly the fixed simulation set and that
the packaged fixed-scenario template asset renders.  It returns 0 only
when every check holds and 1 on any failure — the container and CI health
boundary of the Demo image; no network, credential, Docker, or formal
capability is ever touched.
"""

from __future__ import annotations

import os

from src.vespercode.demo.app import (
    DEMO_CAPABILITY_KINDS_V1,
    DemoAppConfigV1,
    create_demo_app,
)


def _platform_port() -> int | None:
    """The validated platform PORT (1..65535) or None.

    The container reads the platform-injected ``PORT`` (SPEC §8.3);
    missing, non-numeric, and out-of-range values fail the boundary
    closed.
    """
    text = os.environ.get("PORT", "")
    try:
        port = int(text)
    except ValueError:
        return None
    if port < 1 or port > 65535:
        return None
    return port


def main() -> int:
    """Verify PORT, registry, and assets; 0 only when all hold.

    - the platform PORT parses and lies within 1..65535;
    - the app's capability registry is exactly the fixed simulation set
      (no local file, credential, Docker, recovery, persistence, SQLite,
      WinCred, OpenAI, or formal Run capability);
    - the packaged fixed-scenario template asset renders.
    """
    port = _platform_port()
    if port is None:
        return 1
    try:
        app = create_demo_app(DemoAppConfigV1(port=port))
    except Exception:
        return 1
    if app.state.capability_kinds != DEMO_CAPABILITY_KINDS_V1:
        return 1
    try:
        app.state.demo.templates.get_template("demo.html")
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
