# Tumor Normal Variant Dashboard

This dashboard is a local post-processing layer for the tumor-normal SLURM pipeline in this repository.
It is designed to run on your Windows PC after you sync a pipeline output directory from the HPC cluster.

The dashboard does not run the analysis itself. It reads the files already produced by the pipeline, stores a compact local summary in DuckDB, and serves an interactive Streamlit interface for cohort review, patient review, export, and BAM inspection with IGV.

## 1. High-Level Workflow

The intended workflow is:

1. Run the main sequencing / variant-calling pipeline on the HPC cluster.
2. Sync the pipeline output directory to your Windows machine without changing its internal structure.
3. Open `launch_dashboard.cmd`.
4. In the launcher:
   - choose the synced results root
   - choose the local DuckDB path
   - choose the local `igv.min.js` file
   - click `Refresh Database`
   - click `Open Dashboard`

The dashboard is local-first on purpose. This avoids trying to host an interactive app on an HPC login node and avoids problems with no admin rights, port forwarding, and session expiry.

## 2. Files In The Dashboard Folder

The dashboard implementation lives under [dashboard](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard).

Important files:

- [dashboard/launcher.py](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/launcher.py)
  - Tkinter GUI launcher
  - lets you browse for the synced results root, DuckDB file, and local `igv.min.js`
  - starts/stops Streamlit
  - starts/stops the local BAM/BAI file server
  - stores launcher settings in `dashboard/local/launcher_config.json`

- [dashboard/data_server.py](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/data_server.py)
  - local HTTP server for BAM and BAI files
  - supports byte-range requests and CORS
  - required by IGV.js to read indexed BAM files correctly

- [dashboard/refresh_dashboard_data.py](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/refresh_dashboard_data.py)
  - scans the synced results directory
  - parses sample metrics and variant outputs
  - rebuilds the local DuckDB database

- [dashboard/streamlit_app.py](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/streamlit_app.py)
  - Streamlit web app
  - reads DuckDB in read-only mode
  - renders all dashboard tabs

- [dashboard/requirements.txt](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/requirements.txt)
  - Python package requirements for the dashboard

- [dashboard/local](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/local)
  - local runtime files
  - usually contains:
    - `tumor_normal_variant_dashboard.duckdb`
    - `launcher_config.json`
    - `igv.min.js`

- [launch_dashboard.cmd](/c:/Users/HemaLab/Desktop/pipeline/klinakis/launch_dashboard.cmd)
  - double-clickable entrypoint
  - starts the launcher without you having to type commands manually

## 3. Expected Synced Results Structure

The dashboard expects a synced HPC results root containing the same structure produced by the pipeline.

Typical top-level contents look like:

```text
<RESULTS_ROOT>/
  run_flow_klinakis.log
  patient_triplets.tsv
  pon_db.vcf.gz
  pon_db.vcf.gz.tbi
  cohort.sample_map
  pon_db/
  12b_S103/
  12c_S102/
  12n_S101/
  13b_S106/
  13c_S105/
  13n_S104/
  12/
    12n_S101/
      tumor/
      tissue/
  13/
    13n_S104/
      tumor/
      tissue/
```

There are two important kinds of directories:

1. Sample-level directories
- examples: `12b_S103`, `12c_S102`, `12n_S101`
- contain fastp, flagstat, mosdepth, BAM, and related sample files

2. Patient-analysis directories
- examples: `12/12n_S101/`, `13/13n_S104/`
- contain the tumor-vs-blood and tissue-vs-blood variant-calling outputs for one specific tissue analysis

## 4. How Samples Are Interpreted

The dashboard uses the sample name prefix to understand sample type:

- `b` = blood
- `c` = tumor / cancer
- `n` = normal tissue biopsy

Examples:

- `13b_S106` -> patient `13`, sample type `blood`
- `13c_S105` -> patient `13`, sample type `tumor`
- `13n_S104` -> patient `13`, sample type `tissue`

If one patient has multiple tissue samples, each tissue sample becomes a separate patient analysis entry in the dashboard.

## 5. Exactly Which Files The Refresh Script Searches For

The refresh script starts from the synced results root and searches for specific files.

### 5.1 Sample-Level Files

For each sample directory like `13b_S106/`, the refresh script searches for:

- `*_fastp.json`
  - used for total reads before filtering and passed reads after filtering

- `stats/*_view.txt`
  - primary source for `samtools flagstat` parsing

- `stout_sterr/*_flagstat.err`
  - fallback flagstat source if the text file is empty or missing

- `stats/*_before_gencore.mosdepth.summary.txt`
  - used for mean coverage before gencore

- `stats/*_after_gencore.mosdepth.summary.txt`
  - used for mean coverage after gencore

- `stats/*_after_gencore.per-base.bed.gz`
  - used for per-base depth lookup in the patient explorer

- recursively under the sample directory:
  - `*_005_RG.bam`
  - `*_005_RG.bam.bai` or `*_005_RG.bai`
  - used by the IGV alignment viewer

### 5.2 Patient Manifest

The refresh script first looks for:

- `patient_triplets.tsv`

This file is the preferred source for mapping:

- patient ID
- blood sample
- tumor sample
- tissue sample

If `patient_triplets.tsv` is missing, the refresh script falls back to inferring analyses from the directory layout under numeric patient folders.

### 5.3 Patient Analysis Files

For each analysis directory like `13/13n_S104/`, the refresh script expects:

- tumor annotation CSV:
  - `tumor/<patient>_tumor_PASSonly_Annotated.hg38_multianno.csv`

- tissue recovered annotation CSV:
  - `tissue/<patient>_tissue_onlyTumorPassVariants_Annotated.hg38_multianno.csv`

- tumor filtered VCF:
  - `tumor/<patient>_tumor_TN_Filtered.vcf.gz`

- tumor PASS VCF:
  - `tumor/<patient>_tumor_PASSonly.vcf.gz`

- tissue filtered VCF:
  - `tissue/<patient>_tissue_TN_Filtered.vcf.gz`

- tissue PASS VCF:
  - `tissue/<patient>_tissue_PASSonly.vcf.gz`

- tissue recovered VCF:
  - `tissue/<patient>_tissue_onlyTumorPassVariants.vcf.gz`

These are used to count variants and build the patient-level and export tables.

## 6. What Is Parsed From Each File

### 6.1 fastp JSON

From `*_fastp.json`, the dashboard reads:

- total reads before filtering
- total reads after filtering

These are stored as:

- `fastp_total_reads`
- `fastp_passed_reads`

### 6.2 flagstat

From `*_view.txt` or fallback `*_flagstat.err`, the dashboard reads:

- total reads
- mapped reads
- mapped percentage

These are stored as:

- `flagstat_total_reads`
- `flagstat_mapped_reads`
- `flagstat_mapped_pct`

### 6.3 mosdepth summary

From the mosdepth summary files, the dashboard reads mean coverage.

Important detail:
- it uses the `total_region` row if present
- if `total_region` is missing, it falls back to `total`

So for rows like:

```text
total        3088286401 477512050 0.15   0 4596
total_region 65653      52044712  792.72 27 2534
```

it will use `792.72` as the panel mean coverage.

These are stored as:

- `mean_coverage_before_gencore`
- `mean_coverage_after_gencore`

### 6.4 per-base mosdepth BED.GZ

From `*_after_gencore.per-base.bed.gz`, the dashboard performs on-demand lookup of the exact depth at the selected variant position for:

- blood
- tumor
- tissue

This is shown in the patient explorer coverage plot/table.

### 6.5 Annovar CSVs

The dashboard reads both tumor PASS Annovar CSVs and tissue recovered Annovar CSVs.

Required columns for ingestion:

- `Chr`
- `Start`
- `End`
- `Ref`
- `Alt`

Then it tries to resolve annotation columns such as:

- gene
- HGVS / AAChange
- ClinVar
- dbSNP
- COSMIC
- InterVar
- allele frequency
- read depth

The parser is flexible and tries exact names first, then partial matches.

Examples of columns it can use:

- `Gene.refGene`
- `AAChange.refGene`
- `Allele Frequency`
- `AF`
- `VAF`
- `DP`
- `Read Depth`
- `avsnp150`
- `avsnp151`
- any column containing `clinvar`, `clnsig`, `cosmic`, `intervar`

### 6.6 VCF Counts

The dashboard does not fully parse these VCFs into the main tables. It uses them mainly to count records:

- tumor detected variants
- tumor PASS variants
- tissue detected variants
- tissue PASS variants
- tissue recovered variants

These counts are shown in the overview and patient explorer.

## 7. How Data Is Stored Locally

The dashboard stores parsed data in a local DuckDB database.

Default location:

- [dashboard/local/tumor_normal_variant_dashboard.duckdb](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/local/tumor_normal_variant_dashboard.duckdb)

The refresh step rebuilds the database from the synced results root using `create or replace table`.

This means:
- the database is a local summary/cache of the synced results
- it is not the authoritative source of truth
- the authoritative source is still the synced output directory from the pipeline

### 7.1 Database Tables

The refresh script creates these tables:

#### `sample_metrics`

One row per sample directory.

Main fields include:

- sample identity
  - `sample_id`
  - `patient_id`
  - `sample_type_code`
  - `sample_group`

- paths
  - `sample_dir`
  - `stats_dir`
  - `sterr_dir`
  - `fastp_json`
  - `flagstat_txt`
  - `flagstat_err`
  - `mosdepth_before_summary_txt`
  - `mosdepth_after_summary_txt`
  - `per_base_bed_gz`
  - `bam_path`
  - `bai_path`
  - `bam_relpath`
  - `bai_relpath`

- parsed metrics
  - `fastp_total_reads`
  - `fastp_passed_reads`
  - `flagstat_total_reads`
  - `flagstat_mapped_reads`
  - `flagstat_mapped_pct`
  - `mean_coverage_before_gencore`
  - `mean_coverage_after_gencore`

#### `analysis_runs`

One row per patient+tissue analysis.

Main fields include:

- `patient_id`
- `blood_sample_id`
- `tumor_sample_id`
- `tissue_sample_id`
- `analysis_dir`

- file paths
  - `tumor_annotation_csv`
  - `tissue_annotation_csv`
  - `tumor_filtered_vcf`
  - `tumor_pass_vcf`
  - `tissue_filtered_vcf`
  - `tissue_pass_vcf`
  - `tissue_recovered_vcf`

- counts
  - `tumor_detected_variants`
  - `tumor_pass_variants`
  - `tissue_detected_variants`
  - `tissue_pass_variants`
  - `tissue_recovered_variants`

#### `recovered_variants`

One row per tumor PASS variant that was recovered in the tissue force-calling analysis.

Main fields include:

- IDs and coordinates
  - `patient_id`
  - `blood_sample_id`
  - `tumor_sample_id`
  - `tissue_sample_id`
  - `variant_key`
  - `chrom`
  - `pos`
  - `end`
  - `ref`
  - `alt`

- annotation
  - `gene`
  - `hgvs`
  - `clinvar`
  - `dbsnp`
  - `cosmic`
  - `intervar`

- metrics
  - `tumor_af`
  - `tumor_dp`
  - `tissue_af`
  - `tissue_dp`
  - `tumor_filter`
  - `tissue_filter`
  - `recovered_in_tissue`
  - `warning_shared_variant`

- raw row JSON
  - `tumor_row_json`
  - `tissue_row_json`

#### `tumor_pass_variants`

One row per tumor PASS variant, whether or not it matched the tissue recovered table.

This table is used mainly for export.

Main fields include:

- patient/sample identity
- genomic coordinates
- tumor annotation
- tumor AF / DP
- whether it matched in tissue
- tissue AF / DP if matched
- tissue gene / HGVS if matched
- tumor and tissue filter labels
- raw tumor/tissue JSON rows

#### `dashboard_metadata`

Single-row metadata table containing:

- refresh timestamp
- synced results root path used to build the database

## 8. Dashboard Tabs And Functionality

The Streamlit app currently has four tabs.

### 8.1 Cohort Overview

Purpose:
- quick cohort-level summary

Shows:

- database refresh timestamp
- synced results root
- number of patients
- number of sample runs
- number of triplet analyses
- number of recovered variants
- bar plot: tumor PASS variants vs tissue recovered variants per analysis
- sample inventory by sample type
- analysis summary table

### 8.2 Patient Explorer

Purpose:
- detailed inspection of one patient analysis at a time

Selection logic:
- patient is chosen in the sidebar
- analysis is chosen in the sidebar
- if a patient has multiple tissue samples, each tissue analysis appears separately

Shows:

- analysis-level metrics
  - tumor detected
  - tumor PASS
  - tissue detected
  - tissue PASS
  - recovered in tissue

- triplet sample stats table
  - blood, tumor, tissue rows
  - fastp counts
  - flagstat counts
  - flagstat mapped percentage
  - mean coverage before gencore
  - mean coverage after gencore

- recovered variants table
  - warning flag
  - variant key
  - gene
  - HGVS
  - ClinVar
  - tumor AF / DP
  - tissue AF / DP
  - dbSNP
  - COSMIC
  - InterVar

- tissue AF warning threshold slider
  - variants above the threshold are marked in the warning column

- selected variant detail view
  - allele frequency bar plot
  - per-base depth bar plot across blood/tumor/tissue
  - raw tumor Annovar fields
  - raw tissue Annovar fields

- `View in BAM` button
  - stores the selected variant in session state
  - prepares it for the Alignment Viewer tab

### 8.3 Export

Purpose:
- flexible CSV export of tumor PASS variants

Source table:
- `tumor_pass_variants`

Filters:

- export scope
  - current analysis
  - current patient
  - all analyses

- patient list when using all analyses
- tissue sample selection
- gene text filter
- `Only variants matched in tissue`

Selectable export columns include:

- patient/sample IDs
- genomic coordinates
- gene
- HGVS
- ClinVar
- dbSNP
- COSMIC
- InterVar
- tumor AF / DP
- tissue AF / DP
- matched-in-tissue flag
- tumor and tissue filters

The export tab shows a preview table and a `Download CSV` button.

### 8.4 Alignment Viewer

Purpose:
- visual inspection of read evidence in BAM files

Backend pieces involved:

- `streamlit_app.py` for UI
- `data_server.py` for local HTTP byte-range serving of BAM/BAI files
- local `igv.min.js` file for the browser viewer

Current behavior:

- starts from the variant selected in Patient Explorer
- default locus window is configurable in the UI
- loads tumor and tissue BAM tracks by default
- blood BAM is optional via checkbox
- user must click `Load Viewer` explicitly
  - this avoids rerendering IGV on every Streamlit rerun

Track behavior:

- expanded read mode
- coverage displayed
- mismatched bases displayed
- reduced sampling settings kept to improve responsiveness

The tab also shows the resolved BAM and BAI URLs used by IGV.

## 9. BAM / IGV Requirements

For the alignment viewer to work, all of the following are needed:

1. The synced results folder must contain the BAM files.
2. The synced results folder must contain the BAM index files.
3. The launcher must start the local BAM server.
4. The launcher / dashboard must know the local `igv.min.js` path.

Recommended location for IGV.js:

- [dashboard/local/igv.min.js](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/local/igv.min.js)

If the viewer fails, the most common causes are:

- missing `.bai`
- wrong synced results root
- old database that still points to outdated BAM paths
- missing local `igv.min.js`

## 10. What The Launcher Does

The launcher is meant to avoid command-line work after the first setup.

Main capabilities:

- browse for synced results root
- browse for DuckDB file
- browse for local `igv.min.js`
- save these paths
- refresh the local database
- start the local BAM server automatically
- launch Streamlit automatically
- stop Streamlit and BAM server

Saved configuration:

- `dashboard/local/launcher_config.json`

Double-click entrypoint:

- [launch_dashboard.cmd](/c:/Users/HemaLab/Desktop/pipeline/klinakis/launch_dashboard.cmd)

## 11. Installation And First-Time Setup

From the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r dashboard\requirements.txt
```

Then place `igv.min.js` locally, ideally here:

- [dashboard/local/igv.min.js](/c:/Users/HemaLab/Desktop/pipeline/klinakis/dashboard/local/igv.min.js)

After that, normal usage is just:

1. sync results from HPC
2. double-click `launch_dashboard.cmd`
3. refresh database
4. open dashboard

## 12. Manual Commands

These are optional, because the launcher is the preferred interface.

### Manual refresh

```powershell
python dashboard\refresh_dashboard_data.py --results-root C:\Users\<you>\Desktop\klinakis_results --db-path dashboard\local\tumor_normal_variant_dashboard.duckdb
```

### Manual dashboard start

```powershell
streamlit run dashboard\streamlit_app.py -- --db-path dashboard\local\tumor_normal_variant_dashboard.duckdb --data-base-url http://127.0.0.1:8765 --igv-js-path dashboard\local\igv.min.js
```

### Manual BAM server start

```powershell
python dashboard\data_server.py --root C:\Users\<you>\Desktop\klinakis_results --host 127.0.0.1 --port 8765
```

## 13. Syncing Results From HPC To Windows

Recommended approaches:

### Option 1: WinSCP

Use SFTP sync from the HPC results directory to a local Windows folder.
This is the simplest GUI option.

### Option 2: `rsync` through WSL

```bash
rsync -av --progress your_user@your_hpc:/path/to/analysis_output/ /mnt/c/Users/<you>/Desktop/klinakis_results/
```

This is the best incremental sync option.

### Option 3: `scp`

```powershell
scp -r your_user@your_hpc:/path/to/analysis_output C:\Users\<you>\Desktop\klinakis_results
```

This works, but is less efficient for repeated updates.

## 14. Current Assumptions And Limitations

Current assumptions:

- the synced output directory keeps the pipeline folder structure unchanged
- sample IDs are unique in the synced dataset
- patient directories are named correctly as numeric patient IDs
- BAM files end with `*_005_RG.bam`
- BAM indexes exist as `*_005_RG.bam.bai` or `*_005_RG.bai`
- final annotation files follow the current Annovar naming pattern

Important limitation:
- resequenced samples with the same sample ID should be resolved before syncing into the dashboard root
- the dashboard currently assumes one unique sample row per sample ID

Refresh behavior:
- the refresh script rebuilds the database, it does not incrementally upsert yet
- this keeps the logic simple and robust for the current project size

## 15. Summary Of What The Dashboard Gives You

In practical terms, the dashboard gives you:

- a patient-by-patient view of tumor / blood / tissue analyses
- read and coverage QC summaries per sample
- recovered-variant inspection with AF and DP
- tissue warning review based on AF threshold
- CSV export of tumor PASS variants with matched tissue information
- direct BAM inspection of selected variants in tumor, tissue, and optionally blood

That makes it a local review layer on top of the pipeline outputs, rather than a second analysis pipeline.
