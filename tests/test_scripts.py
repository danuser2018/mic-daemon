import os
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
MIC_START_SCRIPT = SCRIPTS_DIR / "mic-start.sh"
MIC_STOP_SCRIPT = SCRIPTS_DIR / "mic-stop.sh"
FLAG_PATH = Path("/tmp/voice_assistant/recording.flag")


def test_mic_start_and_stop_scripts_without_novactl():
    # Filter out any directory from PATH that contains a novactl binary
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    clean_path_dirs = [d for d in path_dirs if d and not (Path(d) / "novactl").exists()]

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(clean_path_dirs)

    # Clean up flag if left by previous tests
    if FLAG_PATH.exists():
        FLAG_PATH.unlink()

    # Test mic-start
    result_start = subprocess.run(
        [str(MIC_START_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result_start.returncode == 1
    assert "Error: novactl is not installed or not in PATH" in result_start.stderr
    assert not FLAG_PATH.exists()

    # Test mic-stop
    result_stop = subprocess.run(
        [str(MIC_STOP_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result_stop.returncode == 1
    assert "Error: novactl is not installed or not in PATH" in result_stop.stderr
    assert not FLAG_PATH.exists()


def test_mic_start_and_stop_scripts_with_mock_novactl(tmp_path):
    # Create a mock novactl binary in temp PATH
    mock_bin_dir = tmp_path / "bin"
    mock_bin_dir.mkdir()
    log_file = tmp_path / "novactl.log"

    mock_novactl = mock_bin_dir / "novactl"
    mock_novactl.write_text(
        f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
exit 0
"""
    )
    mock_novactl.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin_dir}:{env.get('PATH', '')}"

    if FLAG_PATH.exists():
        FLAG_PATH.unlink()

    # Test mic-start
    result_start = subprocess.run(
        [str(MIC_START_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result_start.returncode == 0
    assert "start-capture" in log_file.read_text()
    assert not FLAG_PATH.exists()

    # Test mic-stop
    result_stop = subprocess.run(
        [str(MIC_STOP_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result_stop.returncode == 0
    assert "stop-capture" in log_file.read_text()
    assert not FLAG_PATH.exists()
