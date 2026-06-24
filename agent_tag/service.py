"""Run Agent Tag as a supervised background service.

`agent-tag service install` registers a keep-alive service that runs
`agent-tag serve` at login and restarts it if it crashes — so the bot stays up
across reboots. macOS uses a launchd LaunchAgent; on Linux we emit a systemd
unit for the operator to install. `uninstall` / `status` manage it.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

LABEL = "com.agenttag.bot"


def _repo_root() -> str:
    # Parent of the agent_tag package — lets `python -m agent_tag.cli` resolve
    # whether installed or run from a source checkout.
    return str(Path(__file__).resolve().parent.parent)


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _log_path() -> Path:
    return Path.home() / "Library" / "Logs" / "agent-tag.log"


def _serve_args(host: str, port: int, db: str, token: str | None) -> list[str]:
    args = [
        sys.executable,
        "-m",
        "agent_tag.cli",
        "serve",
        "--host",
        host,
        "--port",
        str(port),
        "--db",
        str(Path(db).resolve()),
    ]
    if token:
        args += ["--token", token]
    return args


def _plist_xml(host: str, port: int, db: str, token: str | None) -> str:
    args = _serve_args(host, port, db, token)
    arg_xml = "\n".join(f"      <string>{a}</string>" for a in args)
    log = _log_path()
    root = _repo_root()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{arg_xml}
  </array>
  <key>WorkingDirectory</key><string>{root}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key><string>{root}</string>
    <key>PATH</key><string>{os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def _systemd_unit(host: str, port: int, db: str, token: str | None) -> str:
    args = " ".join(_serve_args(host, port, db, token))
    return f"""[Unit]
Description=Agent Tag — open AI teammate for group chats
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={_repo_root()}
Environment=PYTHONPATH={_repo_root()}
Environment=PATH={os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}
ExecStart={args}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""


def install(host: str, port: int, db: str, token: str | None) -> int:
    if platform.system() != "Darwin":
        unit = _systemd_unit(host, port, db, token)
        path = Path.home() / ".config" / "systemd" / "user" / "agent-tag.service"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(unit, encoding="utf-8")
        print(f"[agent-tag] wrote systemd unit → {path}")
        print("  Enable it with:")
        print("    systemctl --user daemon-reload && systemctl --user enable --now agent-tag")
        return 0

    plist = _plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    _log_path().parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(_plist_xml(host, port, db, token), encoding="utf-8")
    # Reload: unload first (ignore error if not loaded), then load.
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    res = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[agent-tag] launchctl load failed: {res.stderr.strip()}")
        return 1
    print(f"[agent-tag] installed + started service '{LABEL}'")
    print(f"  plist:  {plist}")
    print(f"  logs:   {_log_path()}")
    print(f"  serves: http://{host}:{port}  ·  db {Path(db).resolve()}")
    print("  Manage: agent-tag service status | uninstall")
    return 0


def uninstall() -> int:
    if platform.system() != "Darwin":
        print("  Disable with: systemctl --user disable --now agent-tag")
        return 0
    plist = _plist_path()
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    if plist.exists():
        plist.unlink()
    print(f"[agent-tag] uninstalled service '{LABEL}'")
    return 0


def status() -> int:
    if platform.system() != "Darwin":
        subprocess.run(["systemctl", "--user", "status", "agent-tag", "--no-pager"])
        return 0
    res = subprocess.run(["launchctl", "list", LABEL], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[agent-tag] service '{LABEL}' is NOT installed.")
        return 1
    pid = "—"
    for line in res.stdout.splitlines():
        s = line.strip()
        if s.startswith('"PID"'):
            pid = s.split("=")[-1].strip().rstrip(";").strip()
    print(f"[agent-tag] service '{LABEL}' is installed.  PID={pid}")
    print(f"  logs: {_log_path()}  (tail -f to watch)")
    return 0
