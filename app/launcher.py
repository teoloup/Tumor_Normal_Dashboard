from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    os.environ.setdefault("TCL_LIBRARY", str(meipass / "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", str(meipass / "_tk_data"))

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
    APP_DIR = PROJECT_ROOT / "app"
else:
    APP_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = APP_DIR.parent

LOCAL_DIR = APP_DIR / "local"
CONFIG_PATH = LOCAL_DIR / "launcher_config.json"
DEFAULT_DB_PATH = LOCAL_DIR / "tumor_normal_variant_dashboard.duckdb"
DEFAULT_IGV_JS_PATH = LOCAL_DIR / "igv.min.js"
REFRESH_SCRIPT = APP_DIR / "refresh_dashboard_data.py"
STREAMLIT_APP = APP_DIR / "streamlit_app.py"
DATA_SERVER_SCRIPT = APP_DIR / "data_server.py"
DATA_SERVER_HOST = "127.0.0.1"
DATA_SERVER_PORT = 8765
DATA_BASE_URL = f"http://{DATA_SERVER_HOST}:{DATA_SERVER_PORT}"
DOCKER_IMAGE = os.environ.get("TNVD_DOCKER_IMAGE", "teoloup/tumor-normal-variant-dashboard:latest")
DOCKER_CONTAINER = "tumor_normal_variant_dashboard"
DEFAULT_LAUNCH_MODE = os.environ.get("TNVD_LAUNCH_MODE", "native")


class DashboardLauncher:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Tumor Normal Variant Dashboard Launcher")
        self.root.geometry("760x440")
        self.root.minsize(700, 400)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        config = self.load_config()

        self.launch_mode_var = tk.StringVar(value=config.get("launch_mode", DEFAULT_LAUNCH_MODE))
        self.results_root_var = tk.StringVar(value=config.get("results_root", ""))
        self.db_path_var = tk.StringVar(value=config.get("db_path", str(DEFAULT_DB_PATH)))
        self.igv_js_path_var = tk.StringVar(value=config.get("igv_js_path", str(DEFAULT_IGV_JS_PATH)))
        self.status_var = tk.StringVar(value="Ready")
        self.streamlit_process: subprocess.Popen[str] | None = None
        self.data_server_process: subprocess.Popen[str] | None = None
        self.data_server_root: str | None = None
        self.refresh_in_progress = False

        self.build_ui()
        self.update_button_state()

    def load_config(self) -> dict:
        if not CONFIG_PATH.exists():
            return {}
        try:
            return json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def native_python_command(self) -> list[str] | None:
        venv_python = APP_DIR / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            return [str(venv_python)]

        if not getattr(sys, "frozen", False):
            return [sys.executable]

        if shutil.which("py"):
            return ["py", "-3"]

        if shutil.which("python"):
            return ["python"]

        return None

    def native_runtime_is_ready(self, python_command: list[str]) -> bool:
        completed = subprocess.run(
            [*python_command, "-c", "import duckdb, pandas, plotly, streamlit"],
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return True
        if completed.stderr:
            self.log(completed.stderr.strip())
        return False

    def require_native_python(self) -> list[str] | None:
        python_command = self.native_python_command()
        if python_command is not None and self.native_runtime_is_ready(python_command):
            return python_command

        setup_script = APP_DIR / "setup_native.cmd"
        should_run_setup = messagebox.askyesno(
            "Native setup required",
            "Native mode needs the dashboard Python dependencies under app\\.venv.\n\n"
            "Run app\\setup_native.cmd now?",
        )
        if should_run_setup and setup_script.exists():
            self.log(f"Running native setup: {setup_script}")
            completed = subprocess.run(["cmd", "/c", str(setup_script)], cwd=str(APP_DIR))
            if completed.returncode == 0:
                python_command = self.native_python_command()
                if python_command is not None and self.native_runtime_is_ready(python_command):
                    self.status_var.set("Native environment ready")
                    return python_command

        messagebox.showerror(
            "Native setup incomplete",
            "Native mode needs the dashboard dependencies installed in app\\.venv.\n\n"
            "Run app\\setup_native.cmd first, or use Docker mode.",
        )
        self.status_var.set("Native environment not ready")
        return None

    def save_config(self) -> None:
        payload = {
            "launch_mode": self.launch_mode_var.get().strip(),
            "results_root": self.results_root_var.get().strip(),
            "db_path": self.db_path_var.get().strip(),
            "igv_js_path": self.igv_js_path_var.get().strip(),
        }
        CONFIG_PATH.write_text(json.dumps(payload, indent=2))

    def build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        title = ttk.Label(frame, text="Tumor Normal Variant Dashboard", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w")

        subtitle = ttk.Label(
            frame,
            text="Select the synced HPC output folder, refresh the local database, then launch the dashboard and BAM viewer.",
        )
        subtitle.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 16))

        ttk.Label(frame, text="Run mode").grid(row=2, column=0, sticky="w", pady=(0, 8))
        self.mode_combo = ttk.Combobox(
            frame,
            textvariable=self.launch_mode_var,
            values=["native", "docker"],
            state="readonly",
        )
        self.mode_combo.grid(row=2, column=1, sticky="w", padx=(8, 8), pady=(0, 8))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_mode_change())

        ttk.Label(frame, text="Synced results root").grid(row=3, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.results_root_var).grid(row=3, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(frame, text="Browse...", command=self.pick_results_root).grid(row=3, column=2, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="DuckDB file").grid(row=4, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.db_path_var).grid(row=4, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(frame, text="Browse...", command=self.pick_db_path).grid(row=4, column=2, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Local IGV.js file").grid(row=5, column=0, sticky="w", pady=(0, 8))
        self.igv_entry = ttk.Entry(frame, textvariable=self.igv_js_path_var)
        self.igv_entry.grid(row=5, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        self.igv_browse_button = ttk.Button(frame, text="Browse...", command=self.pick_igv_js_path)
        self.igv_browse_button.grid(row=5, column=2, sticky="ew", pady=(0, 8))

        info = ttk.Label(frame, text=f"Local BAM server URL: {DATA_BASE_URL}")
        info.grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 8))

        button_row = ttk.Frame(frame)
        button_row.grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 12))

        self.save_button = ttk.Button(button_row, text="Save Paths", command=self.on_save)
        self.save_button.pack(side="left", padx=(0, 8))

        self.refresh_button = ttk.Button(button_row, text="Refresh Database", command=self.on_refresh)
        self.refresh_button.pack(side="left", padx=(0, 8))

        self.open_button = ttk.Button(button_row, text="Open Dashboard", command=self.on_launch_dashboard)
        self.open_button.pack(side="left", padx=(0, 8))

        self.stop_button = ttk.Button(button_row, text="Stop Dashboard", command=self.on_stop_dashboard)
        self.stop_button.pack(side="left", padx=(0, 8))

        self.folder_button = ttk.Button(button_row, text="Open Dashboard Folder", command=self.open_dashboard_folder)
        self.folder_button.pack(side="left")

        status_label = ttk.Label(frame, textvariable=self.status_var, foreground="#1f4d7a")
        status_label.grid(row=8, column=0, columnspan=3, sticky="w")

        ttk.Label(frame, text="Log").grid(row=9, column=0, sticky="w", pady=(12, 4))
        self.log_box = tk.Text(frame, height=14, wrap="word")
        self.log_box.grid(row=10, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(10, weight=1)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_box.yview)
        scrollbar.grid(row=10, column=3, sticky="ns")
        self.log_box.configure(yscrollcommand=scrollbar.set)

        self.log("Launcher ready.")
        self.on_mode_change()

    def is_native_dashboard_running(self) -> bool:
        return self.streamlit_process is not None and self.streamlit_process.poll() is None

    def is_docker_dashboard_running(self) -> bool:
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name=^{DOCKER_CONTAINER}$"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and bool(result.stdout.strip())

    def is_data_server_running(self) -> bool:
        return self.data_server_process is not None and self.data_server_process.poll() is None

    def launch_mode(self) -> str:
        return self.launch_mode_var.get().strip().lower() or "native"

    def update_button_state(self) -> None:
        dashboard_running = self.is_native_dashboard_running() if self.launch_mode() == "native" else self.is_docker_dashboard_running()
        self.open_button.config(state="disabled" if dashboard_running else "normal")
        stop_enabled = dashboard_running or (self.launch_mode() == "native" and self.is_data_server_running())
        self.stop_button.config(state="normal" if stop_enabled else "disabled")
        self.refresh_button.config(state="disabled" if self.refresh_in_progress else "normal")

    def log(self, message: str) -> None:
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def on_mode_change(self) -> None:
        docker_mode = self.launch_mode() == "docker"
        igv_state = "disabled" if docker_mode else "normal"
        self.igv_entry.config(state=igv_state)
        self.igv_browse_button.config(state=igv_state)
        if docker_mode:
            self.status_var.set("Docker mode selected")
        else:
            self.status_var.set("Native mode selected")
        self.update_button_state()

    def pick_results_root(self) -> None:
        selected = filedialog.askdirectory(title="Select synced HPC results root")
        if selected:
            self.results_root_var.set(selected)

    def pick_db_path(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Select DuckDB file",
            defaultextension=".duckdb",
            initialfile=Path(self.db_path_var.get()).name or DEFAULT_DB_PATH.name,
            initialdir=str(Path(self.db_path_var.get()).parent if self.db_path_var.get() else LOCAL_DIR),
            filetypes=[("DuckDB database", "*.duckdb"), ("All files", "*.*")],
        )
        if selected:
            self.db_path_var.set(selected)

    def pick_igv_js_path(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select local igv.min.js",
            initialdir=str(Path(self.igv_js_path_var.get()).parent if self.igv_js_path_var.get() else LOCAL_DIR),
            filetypes=[("JavaScript file", "*.js"), ("All files", "*.*")],
        )
        if selected:
            self.igv_js_path_var.set(selected)

    def validate_inputs(self) -> tuple[Path, Path, Path] | None:
        results_root = Path(self.results_root_var.get().strip())
        db_path = Path(self.db_path_var.get().strip())
        igv_js_path = Path(self.igv_js_path_var.get().strip())

        if not results_root.exists() or not results_root.is_dir():
            messagebox.showerror("Missing results root", "Select a valid synced results directory.")
            return None

        if not self.db_path_var.get().strip():
            messagebox.showerror("Missing database path", "Select a valid DuckDB database path.")
            return None

        if self.launch_mode() == "native" and (
            not self.igv_js_path_var.get().strip() or not igv_js_path.exists() or not igv_js_path.is_file()
        ):
            messagebox.showerror("Missing IGV.js file", "Select a valid local igv.min.js file for the alignment viewer.")
            return None

        db_path.parent.mkdir(parents=True, exist_ok=True)
        return results_root, db_path, igv_js_path

    def ensure_data_server(self, results_root: Path) -> bool:
        python_command = self.require_native_python()
        if python_command is None:
            return False

        desired_root = str(results_root.resolve())
        if self.is_data_server_running() and self.data_server_root == desired_root:
            return True

        if self.is_data_server_running():
            self.stop_data_server()

        command = [
            *python_command,
            str(DATA_SERVER_SCRIPT),
            "--root",
            desired_root,
            "--host",
            DATA_SERVER_HOST,
            "--port",
            str(DATA_SERVER_PORT),
        ]
        self.log("Starting data server: " + " ".join(command))
        try:
            self.data_server_process = subprocess.Popen(command)
        except OSError as exc:
            messagebox.showerror("Data server failed", f"Could not start the local BAM server.\n\n{exc}")
            self.status_var.set("Data server launch failed")
            return False

        self.data_server_root = desired_root
        self.log(f"Local BAM server started at {DATA_BASE_URL}")
        return True

    def stop_data_server(self) -> None:
        if not self.is_data_server_running():
            self.data_server_process = None
            self.data_server_root = None
            return

        assert self.data_server_process is not None
        self.log("Stopping local BAM server...")
        self.data_server_process.terminate()
        try:
            self.data_server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.log("Local BAM server did not stop in time, killing process.")
            self.data_server_process.kill()
            self.data_server_process.wait(timeout=5)

        self.data_server_process = None
        self.data_server_root = None
        self.log("Local BAM server stopped.")

    def stop_dashboard_process(self) -> None:
        if not self.is_native_dashboard_running():
            self.streamlit_process = None
            return

        assert self.streamlit_process is not None
        self.log("Stopping dashboard process...")
        self.streamlit_process.terminate()
        try:
            self.streamlit_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.log("Dashboard did not stop in time, killing process.")
            self.streamlit_process.kill()
            self.streamlit_process.wait(timeout=5)

        self.streamlit_process = None
        self.log("Dashboard process stopped.")

    def stop_services(self) -> None:
        self.stop_dashboard_process()
        self.stop_data_server()
        self.update_button_state()

    def ensure_docker_available(self) -> bool:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            messagebox.showerror("Docker not available", "Docker Desktop was not found or is not available in PATH.")
            self.status_var.set("Docker unavailable")
            return False
        return True

    def ensure_docker_image(self) -> bool:
        inspect = subprocess.run(["docker", "image", "inspect", DOCKER_IMAGE], capture_output=True, text=True)
        if inspect.returncode == 0:
            return True

        self.log(f"Docker image {DOCKER_IMAGE} not found locally. Pulling from Docker Hub...")
        pull = subprocess.run(["docker", "pull", DOCKER_IMAGE], capture_output=True, text=True)
        if pull.stdout:
            self.log(pull.stdout.strip())
        if pull.stderr:
            self.log(pull.stderr.strip())
        if pull.returncode != 0:
            messagebox.showerror(
                "Docker pull failed",
                f"Could not pull the Docker image:\n\n{DOCKER_IMAGE}\n\n"
                "Check Docker Desktop, internet access, and the image name.",
            )
            self.status_var.set("Docker pull failed")
            return False
        return True

    def refresh_docker_database(self, results_root: Path, db_path: Path) -> int:
        command = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{results_root.resolve()}:/data",
            "-v",
            f"{db_path.parent.resolve()}:/state",
            "-e",
            f"TNVD_DB_PATH=/state/{db_path.name}",
            "-e",
            "TNVD_RESULTS_ROOT=/data",
            DOCKER_IMAGE,
            "sh",
            "-lc",
            (
                "if [ -f /app/app/refresh_dashboard_data.py ]; then "
                "python /app/app/refresh_dashboard_data.py --results-root /data --db-path /state/"
                f"{db_path.name}; "
                "elif [ -f /app/dashboard/refresh_dashboard_data.py ]; then "
                "python /app/dashboard/refresh_dashboard_data.py --results-root /data --db-path /state/"
                f"{db_path.name}; "
                "else echo 'Could not find refresh_dashboard_data.py in the container.'; exit 2; fi"
            ),
        ]
        self.log("Running: " + " ".join(command))
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.stdout:
            self.log(completed.stdout.strip())
        if completed.stderr:
            self.log(completed.stderr.strip())
        return completed.returncode

    def launch_docker_dashboard(self, results_root: Path, db_path: Path) -> bool:
        if not self.ensure_docker_available():
            return False
        if not self.ensure_docker_image():
            return False

        subprocess.run(["docker", "rm", "-f", DOCKER_CONTAINER], capture_output=True, text=True)
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            DOCKER_CONTAINER,
            "-p",
            "8501:8501",
            "-p",
            "8765:8765",
            "-v",
            f"{results_root.resolve()}:/data",
            "-v",
            f"{db_path.parent.resolve()}:/state",
            "-e",
            f"TNVD_DB_PATH=/state/{db_path.name}",
            "-e",
            "TNVD_CONTAINER_MODE=1",
            "-e",
            "TNVD_RESULTS_ROOT=/data",
            "-e",
            "TNVD_DATA_PORT=8765",
            "-e",
            "TNVD_STREAMLIT_PORT=8501",
            DOCKER_IMAGE,
            "sh",
            "-lc",
            (
                "if [ -f /app/docker/docker_start.py ]; then "
                "python /app/docker/docker_start.py; "
                "elif [ -f /app/dashboard/docker_start.py ]; then "
                "python /app/dashboard/docker_start.py; "
                "elif [ -f /app/app/streamlit_app.py ] && [ -f /app/app/data_server.py ]; then "
                "python /app/app/data_server.py --root /data --host 0.0.0.0 --port 8765 & "
                "exec python -m streamlit run /app/app/streamlit_app.py "
                "--server.address 0.0.0.0 --server.port 8501 -- "
                "--db-path /state/"
                f"{db_path.name} "
                "--data-base-url http://127.0.0.1:8765 "
                "--igv-js-path /app/app/local/igv.min.js; "
                "elif [ -f /app/dashboard/streamlit_app.py ] && [ -f /app/dashboard/data_server.py ]; then "
                "python /app/dashboard/data_server.py --root /data --host 0.0.0.0 --port 8765 & "
                "exec python -m streamlit run /app/dashboard/streamlit_app.py "
                "--server.address 0.0.0.0 --server.port 8501 -- "
                "--db-path /state/"
                f"{db_path.name} "
                "--data-base-url http://127.0.0.1:8765 "
                "--igv-js-path /app/dashboard/local/igv.min.js; "
                "else echo 'Could not find docker_start.py in the container.'; exit 2; fi"
            ),
        ]
        self.log("Launching Docker dashboard: " + " ".join(command))
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.stdout:
            self.log(completed.stdout.strip())
        if completed.stderr:
            self.log(completed.stderr.strip())
        if completed.returncode != 0:
            messagebox.showerror("Docker launch failed", "Could not start the Docker dashboard container.")
            self.status_var.set("Docker launch failed")
            return False

        subprocess.Popen(["cmd", "/c", "start", "", "http://127.0.0.1:8501"])
        self.status_var.set("Docker dashboard launched")
        return True

    def stop_docker_dashboard(self) -> None:
        self.log("Stopping Docker dashboard container...")
        subprocess.run(["docker", "rm", "-f", DOCKER_CONTAINER], capture_output=True, text=True)
        self.log("Docker dashboard container stopped.")

    def on_save(self) -> None:
        validated = self.validate_inputs()
        if not validated:
            return
        self.save_config()
        self.status_var.set("Saved launcher paths")
        self.log("Saved launcher configuration.")

    def on_refresh(self) -> None:
        validated = self.validate_inputs()
        if not validated:
            return

        results_root, db_path, igv_js_path = validated
        self.save_config()

        if self.launch_mode() == "native":
            if self.is_native_dashboard_running():
                should_stop = messagebox.askyesno(
                    "Stop dashboard",
                    "The dashboard is running and keeps the database open. Stop the dashboard and local BAM server before refreshing?",
                )
                if not should_stop:
                    self.log("Refresh cancelled because the dashboard is still running.")
                    return
                self.stop_services()
        else:
            if not self.ensure_docker_available():
                return
            if not self.ensure_docker_image():
                return
            if self.is_docker_dashboard_running():
                should_stop = messagebox.askyesno(
                    "Stop Docker dashboard",
                    "The Docker dashboard is running. Stop the Docker container before refreshing the database?",
                )
                if not should_stop:
                    self.log("Refresh cancelled because the Docker dashboard is still running.")
                    return
                self.stop_docker_dashboard()

        self.status_var.set("Refreshing database...")
        self.refresh_in_progress = True
        self.update_button_state()

        def worker() -> None:
            if self.launch_mode() == "native":
                python_command = self.require_native_python()
                if python_command is None:
                    self.refresh_in_progress = False
                    self.root.after(0, self.update_button_state)
                    return
                command = [
                    *python_command,
                    str(REFRESH_SCRIPT),
                    "--results-root",
                    str(results_root),
                    "--db-path",
                    str(db_path),
                ]
                self.log("Running: " + " ".join(command))
                completed = subprocess.run(command, capture_output=True, text=True)
                if completed.stdout:
                    self.log(completed.stdout.strip())
                if completed.stderr:
                    self.log(completed.stderr.strip())
                returncode = completed.returncode
            else:
                returncode = self.refresh_docker_database(results_root, db_path)

            self.refresh_in_progress = False
            if returncode == 0:
                self.status_var.set("Database refresh completed")
                self.log("Database refresh completed successfully.")
            else:
                self.status_var.set("Database refresh failed")
                self.log(f"Database refresh failed with exit code {returncode}.")
            self.root.after(0, self.update_button_state)

        threading.Thread(target=worker, daemon=True).start()

    def on_launch_dashboard(self) -> None:
        validated = self.validate_inputs()
        if not validated:
            return

        results_root, db_path, igv_js_path = validated
        self.save_config()

        if self.launch_mode() == "docker":
            if self.is_docker_dashboard_running():
                self.status_var.set("Docker dashboard already running")
                self.log("Docker dashboard is already running.")
                self.update_button_state()
                return
            if self.launch_docker_dashboard(results_root, db_path):
                self.log("Docker dashboard started.")
            self.update_button_state()
            return

        if self.is_native_dashboard_running():
            self.status_var.set("Dashboard already running")
            self.log("Dashboard is already running.")
            self.update_button_state()
            return

        if not self.ensure_data_server(results_root):
            self.update_button_state()
            return

        python_command = self.require_native_python()
        if python_command is None:
            self.stop_data_server()
            self.update_button_state()
            return

        command = [
            *python_command,
            "-m",
            "streamlit",
            "run",
            str(STREAMLIT_APP),
            "--",
            "--db-path",
            str(db_path),
            "--data-base-url",
            DATA_BASE_URL,
            "--igv-js-path",
            str(igv_js_path),
        ]
        self.log("Launching dashboard: " + " ".join(command))
        try:
            self.streamlit_process = subprocess.Popen(command)
        except OSError as exc:
            messagebox.showerror("Launch failed", f"Could not launch Streamlit.\n\n{exc}")
            self.status_var.set("Dashboard launch failed")
            self.stop_data_server()
            self.update_button_state()
            return

        self.status_var.set("Dashboard launched")
        self.log("Dashboard started in a new process.")
        self.update_button_state()

    def on_stop_dashboard(self) -> None:
        if self.launch_mode() == "docker":
            if not self.is_docker_dashboard_running():
                self.status_var.set("Docker dashboard is not running")
                self.log("No running Docker dashboard container was found.")
                self.update_button_state()
                return
            self.stop_docker_dashboard()
            self.status_var.set("Docker dashboard stopped")
            self.update_button_state()
            return

        if not self.is_native_dashboard_running() and not self.is_data_server_running():
            self.status_var.set("Dashboard is not running")
            self.log("No running dashboard or local BAM server process was found.")
            self.update_button_state()
            return

        self.stop_services()
        self.status_var.set("Dashboard stopped")

    def open_dashboard_folder(self) -> None:
        subprocess.Popen(["explorer", str(PROJECT_ROOT)])

    def on_close(self) -> None:
        if self.launch_mode() == "docker":
            if self.is_docker_dashboard_running():
                should_stop = messagebox.askyesno(
                    "Stop Docker dashboard",
                    "The Docker dashboard is still running. Stop the container before closing the launcher?",
                )
                if should_stop:
                    self.stop_docker_dashboard()
        elif self.is_native_dashboard_running() or self.is_data_server_running():
            should_stop = messagebox.askyesno(
                "Stop dashboard",
                "The dashboard or local BAM server is still running. Stop them before closing the launcher?",
            )
            if should_stop:
                self.stop_services()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    DashboardLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
