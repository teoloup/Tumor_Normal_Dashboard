from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    data_root = Path(os.environ.get("TNVD_RESULTS_ROOT", "/data"))
    state_root = Path(os.environ.get("TNVD_STATE_ROOT", "/state"))
    db_path = Path(os.environ.get("TNVD_DB_PATH", str(state_root / "tumor_normal_variant_dashboard.duckdb")))
    igv_js_path = Path(os.environ.get("TNVD_IGV_JS_PATH", "/app/dashboard/local/igv.min.js"))
    streamlit_port = os.environ.get("TNVD_STREAMLIT_PORT", "8501")
    data_port = os.environ.get("TNVD_DATA_PORT", "8765")
    auto_refresh = os.environ.get("TNVD_AUTO_REFRESH", "1") != "0"

    state_root.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)

    if auto_refresh:
        refresh_cmd = [
            sys.executable,
            str(repo_root / "dashboard" / "refresh_dashboard_data.py"),
            "--results-root",
            str(data_root),
            "--db-path",
            str(db_path),
        ]
        refresh = subprocess.run(refresh_cmd)
        if refresh.returncode != 0:
            return refresh.returncode

    data_server_cmd = [
        sys.executable,
        str(repo_root / "dashboard" / "data_server.py"),
        "--root",
        str(data_root),
        "--host",
        "0.0.0.0",
        "--port",
        data_port,
    ]
    data_server = subprocess.Popen(data_server_cmd)

    try:
        streamlit_cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(repo_root / "dashboard" / "streamlit_app.py"),
            "--server.address",
            "0.0.0.0",
            "--server.port",
            streamlit_port,
            "--",
            "--db-path",
            str(db_path),
            "--data-base-url",
            f"http://127.0.0.1:{data_port}",
            "--igv-js-path",
            str(igv_js_path),
        ]
        streamlit = subprocess.run(streamlit_cmd)
        return streamlit.returncode
    finally:
        data_server.terminate()
        try:
            data_server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            data_server.kill()
            data_server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
