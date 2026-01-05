import asyncio
import os
import re
from typing import Any, Dict, List, Sequence, Tuple

# The decky plugin module is located at decky-loader/plugin
# For easy intellisense checkout the decky-loader code repo
# and add the `decky-loader/plugin/imports` path to `python.analysis.extraPaths` in `.vscode/settings.json`
import decky


_UNIT_RE = re.compile(r"^[A-Za-z0-9@._:-]+(?:\\.[A-Za-z0-9@._:-]+)?$")


# Keep this list intentionally small and safety-focused.
# You can expand it later, but avoid turning this plugin into an arbitrary privileged command runner.
DEFAULT_UNITS: List[Dict[str, str]] = [
    {"unit": "sshd.service", "label": "SSH Server"},
    # Common service on SteamOS/Steam Deck (safe to toggle; if missing, UI will show as not found)
    {"unit": "bluetooth.service", "label": "Bluetooth"},
]


class SystemctlError(RuntimeError):
    pass


async def _run_systemctl(args: Sequence[str]) -> Tuple[int, str, str]:
    """Run systemctl safely (no shell). Returns (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "systemctl",
        "--no-pager",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "SYSTEMD_PAGER": "cat",
            "SYSTEMD_COLORS": "0",
        },
    )
    out_b, err_b = await proc.communicate()
    out = (out_b or b"").decode("utf-8", errors="replace").strip()
    err = (err_b or b"").decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, out, err


def _parse_kv_lines(text: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def _normalize_unit(unit: str) -> str:
    unit = (unit or "").strip()
    if not unit:
        raise ValueError("unit is required")
    if not _UNIT_RE.match(unit):
        raise ValueError("invalid unit name")
    # Default to .service units if caller passed a bare name.
    if "." not in unit:
        unit = f"{unit}.service"
    return unit


class Plugin:
    async def _main(self):
        # Keep a reference to the loop for any future async tasks.
        self.loop = asyncio.get_event_loop()
        decky.logger.info("Tower Control backend loaded")

    async def _unload(self):
        decky.logger.info("Tower Control backend unloaded")

    def _allowed_units(self) -> List[Dict[str, str]]:
        # Future: load additional units from settings, but always keep an allowlist.
        return DEFAULT_UNITS

    def _is_allowed(self, unit: str) -> bool:
        allowed = {u["unit"] for u in self._allowed_units()}
        return unit in allowed

    async def _get_unit_status(self, unit: str) -> Dict[str, Any]:
        unit = _normalize_unit(unit)
        rc, out, err = await _run_systemctl(
            [
                "show",
                unit,
                "--property=LoadState,ActiveState,SubState,UnitFileState,Description",
            ]
        )

        # If systemctl fails and returns no structured output, avoid returning a wall of "unknown".
        if rc != 0 and not out:
            # systemctl tends to report missing units via stderr.
            if "not be found" in err or "not-found" in err:
                return {
                    "unit": unit,
                    "exists": False,
                    "active": False,
                    "activeState": "inactive",
                    "subState": "dead",
                    "unitFileState": "not-found",
                    "enabled": False,
                    "canToggleEnable": False,
                    "description": None,
                    "loadState": "not-found",
                }

            decky.logger.warning(f"systemctl show failed for {unit}: rc={rc} err={err}")

        # systemctl show returns rc>0 for not-found units; still parse what we can
        data = _parse_kv_lines(out)
        load_state = data.get("LoadState", "unknown")
        exists = load_state != "not-found"
        active_state = data.get("ActiveState", "unknown")
        sub_state = data.get("SubState", "unknown")
        unit_file_state = data.get("UnitFileState", "unknown")
        desc = data.get("Description")

        enabled = unit_file_state in {"enabled", "enabled-runtime"}
        # "static" units cannot be enabled/disabled. Other states may still be togglable
        # (e.g. masked -> can be unmasked then enabled), so we only hard-disable static.
        can_toggle_enable = unit_file_state != "static"

        return {
            "unit": unit,
            "exists": exists,
            "active": active_state == "active",
            "activeState": active_state,
            "subState": sub_state,
            "unitFileState": unit_file_state,
            "enabled": enabled,
            "canToggleEnable": can_toggle_enable,
            "description": desc,
            "loadState": load_state,
        }

    async def get_services(self) -> List[Dict[str, Any]]:
        """Return a small allowlisted set of systemd services and their status."""
        services: List[Dict[str, Any]] = []
        for entry in self._allowed_units():
            unit = entry["unit"]
            status = await self._get_unit_status(unit)
            services.append({
                "unit": status["unit"],
                "label": entry.get("label", status["unit"]),
                "exists": status["exists"],
                "active": status["active"],
                "activeState": status["activeState"],
                "subState": status["subState"],
                "unitFileState": status["unitFileState"],
                "enabled": status["enabled"],
                "canToggleEnable": status["canToggleEnable"],
                "description": status.get("description"),
                "loadState": status.get("loadState"),
            })
        return services

    async def get_service_status(self, unit: str) -> Dict[str, Any]:
        unit = _normalize_unit(unit)
        if not self._is_allowed(unit):
            raise ValueError("unit is not allowlisted")
        status = await self._get_unit_status(unit)
        return {
            "unit": status["unit"],
            "exists": status["exists"],
            "active": status["active"],
            "activeState": status["activeState"],
            "subState": status["subState"],
            "unitFileState": status["unitFileState"],
            "enabled": status["enabled"],
            "canToggleEnable": status["canToggleEnable"],
            "description": status.get("description"),
            "loadState": status.get("loadState"),
        }

    async def set_service_running(self, unit: str, running: bool) -> Dict[str, Any]:
        """Start/stop an allowlisted unit and return its updated status."""
        unit = _normalize_unit(unit)
        if not self._is_allowed(unit):
            raise ValueError("unit is not allowlisted")

        action = "start" if running else "stop"
        rc, out, err = await _run_systemctl([action, unit])
        if rc != 0:
            msg = err or out or f"systemctl {action} failed"
            raise SystemctlError(msg)

        return await self.get_service_status(unit)

    async def set_service_enabled(self, unit: str, enabled: bool) -> Dict[str, Any]:
        """Enable/disable an allowlisted unit (start on boot), return updated status.

        Note: enabling does not imply starting, and disabling does not imply stopping.
        """
        unit = _normalize_unit(unit)
        if not self._is_allowed(unit):
            raise ValueError("unit is not allowlisted")

        # Inspect current status to handle special states like masked/static.
        current = await self._get_unit_status(unit)
        if enabled and current.get("unitFileState") == "static":
            raise SystemctlError("unit is static and cannot be enabled/disabled")

        if enabled:
            # If masked, unmask first.
            if current.get("unitFileState") == "masked":
                rc, out, err = await _run_systemctl(["unmask", unit])
                if rc != 0:
                    msg = err or out or "systemctl unmask failed"
                    raise SystemctlError(msg)

            rc, out, err = await _run_systemctl(["enable", unit])
            if rc != 0:
                msg = err or out or "systemctl enable failed"
                raise SystemctlError(msg)
        else:
            rc, out, err = await _run_systemctl(["disable", unit])
            if rc != 0:
                msg = err or out or "systemctl disable failed"
                raise SystemctlError(msg)

        return await self.get_service_status(unit)
