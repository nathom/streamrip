import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "docker-entrypoint.sh"


def _run_entrypoint(tmp_path, ids=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    id_capture = tmp_path / "su-exec-id"
    home_capture = tmp_path / "home"
    arg_capture = tmp_path / "argument"
    fake_su_exec = bin_dir / "su-exec"
    fake_su_exec.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$1\" > \"$ID_CAPTURE\"\n"
        "shift\n"
        "export HOME=/\n"
        "exec \"$@\"\n"
    )
    fake_su_exec.chmod(0o755)

    env = os.environ.copy()
    env.pop("PUID", None)
    env.pop("PGID", None)
    env.pop("HOME", None)
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ID_CAPTURE": str(id_capture),
            "HOME_CAPTURE": str(home_capture),
            "ARG_CAPTURE": str(arg_capture),
        }
    )
    if ids:
        env.update(ids)

    result = subprocess.run(
        [
            "sh",
            str(ENTRYPOINT),
            "sh",
            "-c",
            'printf "%s\\n" "$HOME" > "$HOME_CAPTURE"; '
            'printf "%s\\n" "$1" > "$ARG_CAPTURE"',
            "sh",
            "forwarded argument",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, id_capture, home_capture, arg_capture


def test_entrypoint_defaults_ids_and_forwards_command(tmp_path):
    result, id_capture, home_capture, arg_capture = _run_entrypoint(tmp_path)

    assert result.returncode == 0
    assert id_capture.read_text().strip() == "1029:100"
    assert home_capture.read_text().strip() == "/config"
    assert arg_capture.read_text().strip() == "forwarded argument"


def test_entrypoint_uses_configured_ids(tmp_path):
    result, id_capture, home_capture, _ = _run_entrypoint(
        tmp_path, {"PUID": "1234", "PGID": "2345"}
    )

    assert result.returncode == 0
    assert id_capture.read_text().strip() == "1234:2345"
    assert home_capture.read_text().strip() == "/config"


@pytest.mark.parametrize("name", ["PUID", "PGID"])
def test_entrypoint_rejects_non_numeric_ids(tmp_path, name):
    ids = {"PUID": "1234", "PGID": "2345"}
    ids[name] = "invalid"
    result, id_capture, _, _ = _run_entrypoint(tmp_path, ids)

    assert result.returncode != 0
    assert "must contain only digits" in result.stderr
    assert not id_capture.exists()
