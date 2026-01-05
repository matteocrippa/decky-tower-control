# Tower Control (Decky Plugin)

Toggle basic systemd services directly from Decky Loader.

## What it does

- Shows current state (running + enabled).
- Lets you start/stop services.
- Lets you enable/disable services at boot.

Allowlisted services:

- `sshd.service` (SSH Server)
- `bluetooth.service` (Bluetooth)

## Permissions / safety

This plugin runs with `"flags": ["root"]` in `plugin.json` because starting/stopping system services typically requires root.

To reduce risk, the backend only allows controlling a small allowlist of unit names (it will refuse arbitrary units).

## Dev

- Frontend: `src/index.tsx`
- Backend: `main.py`
