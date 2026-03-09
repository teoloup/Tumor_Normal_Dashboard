# Tumor_Normal_Dashboard

Tumor_Normal_Dashboard is a local review dashboard for the tumor-normal variant calling workflow in this repository.

It combines:
- the SLURM/bash pipeline for preprocessing, PoN creation, and tumor-normal calling
- a local Streamlit dashboard for cohort review, patient review, export, and BAM inspection

## Repository Structure

- `Tumor_Normal_Variant_Dashboard_Launcher.exe`
  - optional packaged GUI launcher for end users
- `launch_dashboard.cmd`
  - root launcher for native mode
- `launch_dashboard_docker.cmd`
  - root launcher for Docker mode
- `stop_dashboard_docker.cmd`
  - stops the running Docker container
- `app/`
  - Python application code, native setup, and EXE build files
- `docker/`
  - Dockerfile and Docker image helper commands

## Quick Start On A New Windows PC

1. Clone the repository.
2. Double-click `Tumor_Normal_Variant_Dashboard_Launcher.exe`.
3. In the launcher:
   - choose `native` or `docker`
   - choose your synced HPC results root
   - refresh the database
   - open the dashboard

What happens next:

- `docker` mode
  - Docker Desktop must already be installed and running
  - the launcher pulls `teoloup/tumor-normal-variant-dashboard:latest` automatically if needed
  - then it refreshes the database and starts the container
- `native` mode
  - Python must already be installed on the machine
  - if `app\.venv` is missing or incomplete, the launcher offers to run `app\setup_native.cmd`
  - then it refreshes the database and starts the local dashboard

## Docker Quick Start

If you prefer to run the dashboard inside Docker:

1. Make sure Docker Desktop is installed and running.
2. Double-click `Tumor_Normal_Variant_Dashboard_Launcher.exe` or `launch_dashboard_docker.cmd`.
3. In the launcher, browse to your synced analysis output directory and DuckDB path.
4. Open `http://127.0.0.1:8501` if the browser does not open automatically.

`launch_dashboard_docker.cmd` now opens the same GUI launcher in Docker mode, so you can still browse for:
- synced results root
- DuckDB file location

The root Docker controls are:

- `launch_dashboard_docker.cmd`
  - opens the launcher directly in Docker mode
- `stop_dashboard_docker.cmd`
  - stops and removes the running dashboard container

Extra Docker image commands live under `docker/`:

- `docker\pull_image.cmd`
  - manually pulls the published Docker image
- `docker\build_image.cmd`
  - builds the Docker image locally from the current source tree

By default, the launcher and Docker scripts use:

- `teoloup/tumor-normal-variant-dashboard:latest`

If you ever want to use a different image tag, set `TNVD_DOCKER_IMAGE` before running the setup or launcher scripts.

## Build A Windows Launcher EXE

If you want to distribute the GUI launcher without requiring Python on the target PC:

1. Run `app\build_launcher.cmd`
2. Wait for the PyInstaller build to finish
3. Distribute the generated root executable:
   - `Tumor_Normal_Variant_Dashboard_Launcher.exe`

The generated executable is:

- `Tumor_Normal_Variant_Dashboard_Launcher.exe`

Notes:

- Docker Desktop is still required if the user wants Docker mode
- native mode still needs Python installed on the PC
- the EXE keeps the repository root clean and launches the same GUI workflow

## Dashboard Notes

The dashboard code lives under `app/`:

- `app/refresh_dashboard_data.py`
  - scans the synced results folder and rebuilds the DuckDB database
- `app/streamlit_app.py`
  - Streamlit UI for cohort review, patient review, export, and IGV/BAM viewing
- `app/data_server.py`
  - lightweight local file server for BAM and BAI access
- `app/requirements.txt`
  - Python dependencies for the native dashboard setup

The local runtime files are stored under `app/local/`, including:

- `launcher_config.json`
- `tumor_normal_variant_dashboard.duckdb`
- `igv.min.js`
