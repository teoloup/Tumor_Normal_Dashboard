# Tumor_Normal_Dashboard

Tumor_Normal_Dashboard is a local review dashboard for the tumor-normal variant calling workflow in this repository.

It combines:
- the SLURM/bash pipeline for preprocessing, PoN creation, and tumor-normal calling
- a local Streamlit dashboard for cohort review, patient review, export, and BAM inspection

## Repository Structure

- `klinakis_agilent_fastp_gencore.sh`
  - sample preprocessing
- `make_pon_klinakis.sh`
  - panel of normals creation
- `run_flow_klinakis_BTC.sh`
  - SLURM flow/orchestration
- `Variant_calling_TN_till_annotation.sh`
  - tumor-vs-blood and tissue-vs-blood analysis
- `dashboard/`
  - local dashboard app
- `setup_dashboard.cmd`
  - one-click Windows setup for a fresh clone
- `launch_dashboard.cmd`
  - one-click launcher after setup

## Quick Start On A New Windows PC

1. Clone the repository.
2. Double-click `setup_dashboard.cmd` once.
3. Double-click `launch_dashboard.cmd`.
4. In the launcher:
   - choose your synced HPC results root
   - refresh the database
   - open the dashboard

## Docker Quick Start

If you prefer to run the dashboard inside Docker:

1. Sync your analysis outputs into the repository `data/` folder.
2. Double-click `setup_docker_dashboard.cmd`.
3. Double-click `launch_dashboard_docker.cmd`.
4. Open `http://127.0.0.1:8501` if the browser does not open automatically.

`launch_dashboard_docker.cmd` now opens the same GUI launcher in Docker mode, so you can still browse for:
- synced results root
- DuckDB file location

Docker helper scripts:

- `setup_docker_dashboard.cmd`
  - builds the Docker image
- `launch_dashboard_docker.cmd`
  - opens the launcher directly in Docker mode
- `stop_dashboard_docker.cmd`
  - stops and removes the running dashboard container

## Build A Windows Launcher EXE

If you want to distribute the GUI launcher without requiring Python on the target PC:

1. Double-click `build_launcher.cmd`
2. Wait for the PyInstaller build to finish
3. Distribute the folder:
   - `dist\Tumor_Normal_Variant_Dashboard_Launcher\`

The generated executable is:

- `dist\Tumor_Normal_Variant_Dashboard_Launcher\Tumor_Normal_Variant_Dashboard_Launcher.exe`

Notes:

- Docker Desktop is still required if the user wants Docker mode
- the launcher EXE only replaces the Python dependency for the GUI launcher

## Detailed Dashboard Documentation

See [dashboard/README.md](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/README.md) for:
- expected results structure
- exact file discovery patterns
- DuckDB schema
- tab functionality
- IGV/BAM viewer behavior
