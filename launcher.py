from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BASE_DIR = Path(__file__).resolve().parent
LOCAL_DIR = BASE_DIR / "local"
CONFIG_PATH = LOCAL_DIR / "launcher_config.json"
DEFAULT_DB_PATH = LOCAL_DIR / "tumor_normal_variant_dashboard.duckdb"
DEFAULT_IGV_JS_PATH = LOCAL_DIR / "igv.min.js"
REFRESH_SCRIPT = BASE_DIR / "refresh_dashboard_data.py"
STREAMLIT_APP = BASE_DIR / "streamlit_app.py"
DATA_SERVER_SCRIPT = BASE_DIR / "data_server.py"
DATA_SERVER_HOST = "127.0.0.1"
DATA_SERVER_PORT = 8765
DATA_BASE_URL = f"http://{DATA_SERVER_HOST}:{DATA_SERVER_PORT}"


class DashboardLauncher:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Tumor Normal Variant Dashboard Launcher")
        self.root.geometry("760x440")
        self.root.minsize(700, 400)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        config = self.load_config()

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

    def save_config(self) -> None:
        payload = {
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

        ttk.Label(frame, text="Synced results root").grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.results_root_var).grid(row=2, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(frame, text="Browse...", command=self.pick_results_root).grid(row=2, column=2, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="DuckDB file").grid(row=3, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.db_path_var).grid(row=3, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(frame, text="Browse...", command=self.pick_db_path).grid(row=3, column=2, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Local IGV.js file").grid(row=4, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(frame, textvariable=self.igv_js_path_var).grid(row=4, column=1, sticky="ew", padx=(8, 8), pady=(0, 8))
        ttk.Button(frame, text="Browse...", command=self.pick_igv_js_path).grid(row=4, column=2, sticky="ew", pady=(0, 8))

        info = ttk.Label(frame, text=f"Local BAM server URL: {DATA_BASE_URL}")
        info.grid(row=5, column=0, columnspan=3, sticky="w", pady=(0, 8))

        button_row = ttk.Frame(frame)
        button_row.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 12))

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
        status_label.grid(row=7, column=0, columnspan=3, sticky="w")

        ttk.Label(frame, text="Log").grid(row=8, column=0, sticky="w", pady=(12, 4))
        self.log_box = tk.Text(frame, height=14, wrap="word")
        self.log_box.grid(row=9, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(9, weight=1)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_box.yview)
        scrollbar.grid(row=9, column=3, sticky="ns")
        self.log_box.configure(yscrollcommand=scrollbar.set)

        self.log("Launcher ready.")

    def is_dashboard_running(self) -> bool:
        return self.streamlit_process is not None and self.streamlit_process.poll() is None

    def is_data_server_running(self) -> bool:
        return self.data_server_process is not None and self.data_server_process.poll() is None

    def update_button_state(self) -> None:
        dashboard_running = self.is_dashboard_running()
        self.open_button.config(state="disabled" if dashboard_running else "normal")
        self.stop_button.config(state="normal" if dashboard_running or self.is_data_server_running() else "disabled")
        self.refresh_button.config(state="disabled" if self.refresh_in_progress else "normal")

    def log(self, message: str) -> None:
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

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

        if not self.igv_js_path_var.get().strip() or not igv_js_path.exists() or not igv_js_path.is_file():
            messagebox.showerror("Missing IGV.js file", "Select a valid local igv.min.js file for the alignment viewer.")
            return None

        db_path.parent.mkdir(parents=True, exist_ok=True)
        return results_root, db_path, igv_js_path

    def ensure_data_server(self, results_root: Path) -> bool:
        desired_root = str(results_root.resolve())
        if self.is_data_server_running() and self.data_server_root == desired_root:
            return True

        if self.is_data_server_running():
            self.stop_data_server()

        command = [
            sys.executable,
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
        if not self.is_dashboard_running():
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

        if self.is_dashboard_running():
            should_stop = messagebox.askyesno(
                "Stop dashboard",
                "The dashboard is running and keeps the database open. Stop the dashboard and local BAM server before refreshing?",
            )
            if not should_stop:
                self.log("Refresh cancelled because the dashboard is still running.")
                return
            self.stop_services()

        self.status_var.set("Refreshing database...")
        self.refresh_in_progress = True
        self.update_button_state()

        def worker() -> None:
            command = [
                sys.executable,
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

            self.refresh_in_progress = False
            if completed.returncode == 0:
                self.status_var.set("Database refresh completed")
                self.log("Database refresh completed successfully.")
            else:
                self.status_var.set("Database refresh failed")
                self.log(f"Database refresh failed with exit code {completed.returncode}.")
            self.root.after(0, self.update_button_state)

        threading.Thread(target=worker, daemon=True).start()

    def on_launch_dashboard(self) -> None:
        validated = self.validate_inputs()
        if not validated:
            return

        results_root, db_path, igv_js_path = validated
        self.save_config()

        if self.is_dashboard_running():
            self.status_var.set("Dashboard already running")
            self.log("Dashboard is already running.")
            self.update_button_state()
            return

        if not self.ensure_data_server(results_root):
            self.update_button_state()
            return

        command = [
            sys.executable,
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
        if not self.is_dashboard_running() and not self.is_data_server_running():
            self.status_var.set("Dashboard is not running")
            self.log("No running dashboard or local BAM server process was found.")
            self.update_button_state()
            return

        self.stop_services()
        self.status_var.set("Dashboard stopped")

    def open_dashboard_folder(self) -> None:
        subprocess.Popen(["explorer", str(BASE_DIR)])

    def on_close(self) -> None:
        if self.is_dashboard_running() or self.is_data_server_running():
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
