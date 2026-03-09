from __future__ import annotations

import argparse
import gzip
import json
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "local" / "tumor_normal_variant_dashboard.duckdb"
DEFAULT_DATA_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_IGV_JS_PATH = Path(__file__).resolve().parent / "local" / "igv.min.js"
LOW_COVERAGE_THRESHOLD = 30
RUNNING_IN_DOCKER = os.environ.get("TNVD_CONTAINER_MODE") == "1"


@st.cache_resource
def get_connection(db_path: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--data-base-url", default=DEFAULT_DATA_BASE_URL)
    parser.add_argument("--igv-js-path", default=str(DEFAULT_IGV_JS_PATH))
    args, _ = parser.parse_known_args()
    return args


def run_query(con: duckdb.DuckDBPyConnection, query: str, params: list | None = None) -> pd.DataFrame:
    return con.execute(query, params or []).fetchdf()


def table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    return bool(con.execute(
        "select count(*) from information_schema.tables where table_name = ?",
        [table_name],
    ).fetchone()[0])


def ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frame = df.copy()
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame


def normalize_chrom(value: str) -> str:
    text = str(value).strip()
    return text[3:] if text.lower().startswith("chr") else text


def build_file_url(base_url: str, relative_path: str) -> str:
    return base_url.rstrip("/") + "/" + quote(relative_path.lstrip("/"), safe="/")


@st.cache_data(show_spinner=False)
def load_igv_js(local_path: str) -> str | None:
    path = Path(local_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


@st.cache_data(show_spinner=False)
def lookup_per_base_depth(per_base_bed_gz: str, chrom: str, pos: int) -> Optional[float]:
    if not per_base_bed_gz:
        return None

    path = Path(per_base_bed_gz)
    if not path.exists():
        return None

    target_chrom = normalize_chrom(chrom)
    try:
        with gzip.open(path, "rt") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 4:
                    continue

                row_chrom = normalize_chrom(parts[0])
                if row_chrom != target_chrom:
                    continue

                start = int(parts[1])
                end = int(parts[2])
                depth = float(parts[3])
                if start < pos <= end:
                    return depth
                if start >= pos:
                    return None
    except (OSError, ValueError):
        return None

    return None


def load_variant_details(raw_json: str) -> pd.DataFrame:
    if not raw_json:
        return pd.DataFrame(columns=["field", "value"])
    payload = json.loads(raw_json)
    return pd.DataFrame({"field": list(payload.keys()), "value": list(payload.values())})


def format_metric(value: object) -> str:
    if value is None or pd.isna(value):
        return "NA"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def build_download_filename(scope: str, patient_id: str, tissue_sample_id: str) -> str:
    if scope == "Current analysis":
        return f"patient_{patient_id}_{tissue_sample_id}_tumor_pass_export.csv"
    if scope == "Current patient":
        return f"patient_{patient_id}_tumor_pass_export.csv"
    return "tumor_normal_variant_dashboard_export.csv"


def render_igv_browser(igv_js_path: str, locus: str, tracks: list[dict[str, str]]) -> None:
    browser_id = f"igv-browser-{abs(hash((locus, tuple(track['name'] for track in tracks))))}"
    status_id = f"igv-status-{abs(hash((locus, len(tracks))))}"
    tracks_json = json.dumps(tracks)
    igv_js = load_igv_js(igv_js_path)
    browser_height = max(520, min(340 + len(tracks) * 190, 980))
    frame_height = browser_height + 60

    if not igv_js:
        st.error(f"Local IGV.js file not found or unreadable: {igv_js_path}")
        st.info("Place igv.min.js in app/local/ or select it in the launcher before opening the dashboard.")
        return

    html = f"""
    <html>
      <head>
        <style>
          html, body {{
            margin: 0;
            padding: 0;
            background: #ffffff;
            color: #111827;
            font-family: Segoe UI, sans-serif;
            overflow-y: auto;
          }}
          #{status_id} {{
            padding: 10px 12px;
            margin-bottom: 8px;
            border: 1px solid #d1d5db;
            background: #f9fafb;
            font-size: 13px;
          }}
          #{browser_id} {{
            width: 100%;
            height: {browser_height}px;
            border: 1px solid #d1d5db;
            background: #ffffff;
          }}
        </style>
      </head>
      <body>
        <div id="{status_id}">Loading IGV viewer...</div>
        <div id="{browser_id}"></div>
        <script>{igv_js}</script>
        <script>
          (async function () {{
            const status = document.getElementById('{status_id}');
            try {{
              if (typeof igv === 'undefined') {{
                throw new Error('IGV.js did not initialize from the local file.');
              }}
              status.textContent = 'Initializing IGV...';
              const options = {{
                genome: 'hg38',
                locus: '{locus}',
                showNavigation: true,
                showChromosomeWidget: true,
                tracks: {tracks_json}
              }};
              await igv.createBrowser(document.getElementById('{browser_id}'), options);
              status.style.display = 'none';
            }} catch (error) {{
              console.error(error);
              status.style.display = 'block';
              status.textContent = 'IGV failed to load: ' + error;
            }}
          }})();
        </script>
      </body>
    </html>
    """
    components.html(html, height=frame_height, scrolling=True)


def main() -> None:
    args = parse_args()
    st.set_page_config(page_title="Tumor Normal Variant Dashboard", layout="wide")

    st.title("Tumor Normal Variant Dashboard")
    st.caption("Local dashboard for reviewing patient-level results after syncing pipeline outputs from the HPC cluster.")
    if RUNNING_IN_DOCKER:
        st.warning("Docker mode: closing the browser does not stop the container. Use the launcher Stop Dashboard button or run stop_dashboard_docker.cmd.")
        if st.button("Stop Docker Dashboard", key="stop_docker_dashboard"):
            os._exit(0)
        components.html(
            """
            <script>
            window.addEventListener("beforeunload", function (event) {
              event.preventDefault();
              event.returnValue = "";
            });
            </script>
            """,
            height=0,
        )

    db_path = st.sidebar.text_input("DuckDB path", value=args.db_path)
    data_base_url = st.sidebar.text_input("Local data server", value=args.data_base_url)
    igv_js_path = st.sidebar.text_input("Local IGV.js file", value=args.igv_js_path)
    db_file = Path(db_path)
    if not db_file.exists():
        st.error(f"Database not found: {db_file}")
        st.code(f"python app/refresh_dashboard_data.py --results-root <SYNCED_RESULTS_DIR> --db-path {db_file}")
        st.stop()

    con = get_connection(str(db_file))
    metadata = run_query(con, "select * from dashboard_metadata") if table_exists(con, "dashboard_metadata") else pd.DataFrame()
    samples = run_query(con, "select * from sample_metrics") if table_exists(con, "sample_metrics") else pd.DataFrame()
    analyses = run_query(con, "select * from analysis_runs order by patient_id, tissue_sample_id") if table_exists(con, "analysis_runs") else pd.DataFrame()
    warnings_df = run_query(con, "select * from refresh_warnings order by warning_type, patient_id, tissue_sample_id") if table_exists(con, "refresh_warnings") else pd.DataFrame()
    recovered = run_query(con, "select * from recovered_variants order by patient_id, tissue_sample_id, chrom, pos") if table_exists(con, "recovered_variants") else pd.DataFrame()
    tumor_pass = run_query(con, "select * from tumor_pass_variants order by patient_id, tissue_sample_id, chrom, pos") if table_exists(con, "tumor_pass_variants") else pd.DataFrame()
    tissue_variants = run_query(con, "select * from tissue_variants order by patient_id, tissue_sample_id, chrom, pos") if table_exists(con, "tissue_variants") else pd.DataFrame()

    samples = ensure_columns(samples, [
        "sample_id",
        "sample_group",
        "fastp_total_reads",
        "fastp_passed_reads",
        "flagstat_total_reads",
        "flagstat_mapped_reads",
        "flagstat_mapped_pct",
        "mean_coverage_before_gencore",
        "mean_coverage_after_gencore",
        "before_per_base_bed_gz",
        "after_per_base_bed_gz",
        "bam_relpath",
        "bai_relpath",
    ])
    warnings_df = ensure_columns(warnings_df, [
        "warning_type",
        "scope",
        "patient_id",
        "sample_id",
        "tissue_sample_id",
        "details",
    ])
    recovered = ensure_columns(recovered, [
        "patient_id",
        "tissue_sample_id",
        "variant_key",
        "gene",
        "hgvs",
        "clinvar",
        "tumor_af",
        "tumor_dp",
        "tissue_af",
        "tissue_dp",
        "dbsnp",
        "cosmic",
        "intervar",
        "chrom",
        "pos",
        "ref",
        "alt",
        "tumor_row_json",
        "tissue_row_json",
    ])
    tissue_variants = ensure_columns(tissue_variants, [
        "patient_id",
        "tissue_sample_id",
        "variant_key",
        "gene",
        "hgvs",
        "clinvar",
        "tissue_af",
        "tissue_dp",
        "matched_in_tumor",
        "tumor_af",
        "tumor_dp",
        "dbsnp",
        "cosmic",
        "intervar",
        "chrom",
        "pos",
        "ref",
        "alt",
        "tissue_row_json",
        "tumor_row_json",
    ])
    tumor_pass = ensure_columns(tumor_pass, [
        "patient_id",
        "tissue_sample_id",
        "tumor_sample_id",
        "blood_sample_id",
        "variant_key",
        "gene",
        "hgvs",
        "clinvar",
        "dbsnp",
        "cosmic",
        "intervar",
        "tumor_af",
        "tumor_dp",
        "matched_in_tissue",
        "tissue_af",
        "tissue_dp",
        "tissue_gene",
        "tissue_hgvs",
        "tumor_filter",
        "tissue_filter",
    ])

    if "alignment_variant" not in st.session_state:
        st.session_state.alignment_variant = None
    if "alignment_render_requested" not in st.session_state:
        st.session_state.alignment_render_requested = False
    if "alignment_show_blood" not in st.session_state:
        st.session_state.alignment_show_blood = False

    selected_patient = None
    analysis_row = None
    patient_ids: list[str] = []
    if not analyses.empty:
        patient_ids = sorted(analyses["patient_id"].dropna().unique().tolist(), key=lambda value: int(str(value)))
        selected_patient = st.sidebar.selectbox("Patient", patient_ids)
        patient_analyses = analyses[analyses["patient_id"] == selected_patient].copy()
        patient_labels = [f"{row['tissue_sample_id']} | tumor={row['tumor_sample_id']} | blood={row['blood_sample_id']}" for _, row in patient_analyses.iterrows()]
        selected_label = st.sidebar.selectbox("Analysis", patient_labels)
        selected_idx = patient_labels.index(selected_label)
        analysis_row = patient_analyses.iloc[selected_idx]

    overview_tab, patient_tab, export_tab, alignment_tab = st.tabs(["Cohort Overview", "Patient Explorer", "Export", "Alignment Viewer"])

    with overview_tab:
        refreshed_at = metadata.iloc[0]["refreshed_at"] if not metadata.empty else "unknown"
        results_root = metadata.iloc[0]["results_root"] if not metadata.empty else "unknown"
        st.write(f"Database refreshed: `{refreshed_at}`")
        st.write(f"Synced results root: `{results_root}`")

        metric_a, metric_b, metric_c, metric_d = st.columns(4)
        metric_a.metric("Patients", analyses["patient_id"].nunique() if "patient_id" in analyses.columns else 0)
        metric_b.metric("Sample Runs", len(samples))
        metric_c.metric("Triplet Analyses", len(analyses))
        metric_d.metric("Recovered Variants", len(recovered))

        if not warnings_df.empty:
            st.subheader("Refresh Warnings")
            st.warning(f"{len(warnings_df)} warning(s) were detected while comparing patient_triplets.tsv against the synced results tree.")
            st.dataframe(warnings_df, width="stretch", hide_index=True)

        if not analyses.empty:
            summary = analyses[[
                "patient_id",
                "tissue_sample_id",
                "tumor_detected_variants",
                "tumor_pass_variants",
                "tissue_detected_variants",
                "tissue_pass_variants",
                "tissue_recovered_variants",
            ]].copy()

            st.subheader("Variant Counts Per Analysis")
            chart_df = summary.melt(
                id_vars=["patient_id", "tissue_sample_id"],
                value_vars=["tumor_pass_variants", "tissue_recovered_variants"],
                var_name="metric",
                value_name="variant_count",
            )
            chart_df["analysis_label"] = chart_df["patient_id"] + " / " + chart_df["tissue_sample_id"]
            fig = px.bar(
                chart_df,
                x="analysis_label",
                y="variant_count",
                color="metric",
                barmode="group",
                labels={"analysis_label": "Analysis", "variant_count": "Variants"},
            )
            st.plotly_chart(fig, width="stretch")

            st.subheader("Sample Inventory")
            sample_counts = samples.groupby("sample_group", dropna=False).size().reset_index(name="count")
            fig_samples = px.bar(sample_counts, x="sample_group", y="count", color="sample_group")
            st.plotly_chart(fig_samples, width="stretch")

            st.subheader("Analysis Summary")
            st.dataframe(summary, width="stretch", hide_index=True)

    with patient_tab:
        if analyses.empty or analysis_row is None or selected_patient is None:
            st.info("No analyses were found in the dashboard database yet.")
        else:
            st.subheader(f"Patient {selected_patient}")
            stat_a, stat_b, stat_c, stat_d, stat_e = st.columns(5)
            stat_a.metric("Tumor detected", format_metric(analysis_row["tumor_detected_variants"]))
            stat_b.metric("Tumor PASS", format_metric(analysis_row["tumor_pass_variants"]))
            stat_c.metric("Tissue detected", format_metric(analysis_row["tissue_detected_variants"]))
            stat_d.metric("Tissue PASS", format_metric(analysis_row["tissue_pass_variants"]))
            stat_e.metric("Recovered in tissue", format_metric(analysis_row["tissue_recovered_variants"]))

            st.subheader("Triplet Sample Stats")
            sample_ids = [analysis_row["blood_sample_id"], analysis_row["tumor_sample_id"], analysis_row["tissue_sample_id"]]
            sample_table = samples[samples["sample_id"].isin(sample_ids)][[
                "sample_id",
                "sample_group",
                "fastp_total_reads",
                "fastp_passed_reads",
                "flagstat_total_reads",
                "flagstat_mapped_reads",
                "flagstat_mapped_pct",
                "mean_coverage_before_gencore",
                "mean_coverage_after_gencore",
            ]].copy()
            st.dataframe(sample_table, width="stretch", hide_index=True)

            show_all_tissue = st.checkbox("Show all tissue variants", value=False, key="patient_show_all_tissue")
            patient_recovered = recovered[
                (recovered["patient_id"] == selected_patient)
                & (recovered["tissue_sample_id"] == analysis_row["tissue_sample_id"])
            ].copy()
            patient_tissue_variants = tissue_variants[
                (tissue_variants["patient_id"] == selected_patient)
                & (tissue_variants["tissue_sample_id"] == analysis_row["tissue_sample_id"])
            ].copy()

            variant_table_label = "All Tissue PASS Variants" if show_all_tissue else "Recovered Variants"
            st.subheader(variant_table_label)
            current_variant_df = patient_tissue_variants if show_all_tissue else patient_recovered
            if current_variant_df.empty:
                st.info(f"No variants were found for this patient analysis in `{variant_table_label}`.")
            else:
                display_columns = [
                    "variant_key",
                    "gene",
                    "hgvs",
                    "clinvar",
                    "tumor_af",
                    "tumor_dp",
                    "tissue_af",
                    "tissue_dp",
                    "dbsnp",
                    "cosmic",
                    "intervar",
                ]
                if show_all_tissue:
                    display_columns.insert(4, "matched_in_tumor")

                st.dataframe(current_variant_df[display_columns], width="stretch", hide_index=True)

                option_labels = current_variant_df.apply(
                    lambda row: (
                        f"{row['variant_key']} | {row['gene']} | "
                        f"tumor AF={format_metric(row['tumor_af'])} | tissue AF={format_metric(row['tissue_af'])}"
                    ),
                    axis=1,
                ).tolist()
                selected_variant_label = st.selectbox("Variant details", option_labels)
                variant_idx = option_labels.index(selected_variant_label)
                variant_row = current_variant_df.iloc[variant_idx]

                if st.button("View in BAM", key="view_in_bam"):
                    st.session_state.alignment_variant = {
                        "patient_id": selected_patient,
                        "tissue_sample_id": analysis_row["tissue_sample_id"],
                        "variant_key": variant_row["variant_key"],
                        "chrom": str(variant_row["chrom"]),
                        "pos": int(variant_row["pos"]),
                        "ref": str(variant_row["ref"]),
                        "alt": str(variant_row["alt"]),
                        "blood_sample_id": analysis_row["blood_sample_id"],
                        "tumor_sample_id": analysis_row["tumor_sample_id"],
                        "tissue_sample_id_full": analysis_row["tissue_sample_id"],
                    }
                    st.session_state.alignment_render_requested = False
                    st.info("Variant stored for the Alignment Viewer tab. Open the Alignment Viewer tab and click Load Viewer to inspect the locus.")

                st.subheader("Allele Frequency")
                af_records = [
                    {"sample_id": analysis_row["tumor_sample_id"], "sample_group": "tumor", "value": variant_row["tumor_af"]},
                    {"sample_id": analysis_row["tissue_sample_id"], "sample_group": "tissue", "value": variant_row["tissue_af"]},
                ]
                af_df = pd.DataFrame(af_records)
                af_fig = px.bar(
                    af_df,
                    x="sample_id",
                    y="value",
                    color="sample_group",
                    labels={"value": "Allele frequency", "sample_id": "Sample"},
                    text="value",
                )
                af_fig.update_traces(texttemplate="%{text}", textposition="outside")
                st.plotly_chart(af_fig, width="stretch")

                st.subheader("Per-Base Coverage Across Blood / Tumor / Tissue")
                coverage_records = []
                for sample_id in sample_ids:
                    sample_row = samples[samples["sample_id"] == sample_id].iloc[0]
                    before_depth = lookup_per_base_depth(sample_row["before_per_base_bed_gz"], variant_row["chrom"], int(variant_row["pos"]))
                    after_depth = lookup_per_base_depth(sample_row["after_per_base_bed_gz"], variant_row["chrom"], int(variant_row["pos"]))
                    coverage_records.append({
                        "sample_id": sample_id,
                        "sample_group": sample_row["sample_group"],
                        "chrom": variant_row["chrom"],
                        "pos": int(variant_row["pos"]),
                        "before_gencore_depth": before_depth,
                        "after_gencore_depth": after_depth,
                    })

                coverage_df = pd.DataFrame(coverage_records)
                coverage_plot_df = coverage_df.melt(
                    id_vars=["sample_id", "sample_group", "chrom", "pos"],
                    value_vars=["before_gencore_depth", "after_gencore_depth"],
                    var_name="stage",
                    value_name="depth",
                )
                coverage_plot_df["stage"] = coverage_plot_df["stage"].map({
                    "before_gencore_depth": "before_gencore",
                    "after_gencore_depth": "after_gencore",
                })
                coverage_fig = px.bar(
                    coverage_plot_df,
                    x="sample_id",
                    y="depth",
                    color="stage",
                    barmode="group",
                    labels={"depth": "Per-base depth", "sample_id": "Sample", "stage": "Stage"},
                )
                st.plotly_chart(coverage_fig, width="stretch")
                st.dataframe(coverage_df, width="stretch", hide_index=True)

                if pd.notna(variant_row["tumor_af"]):
                    low_coverage_samples = coverage_df[
                        coverage_df["sample_group"].isin(["blood", "tissue"])
                        & (
                            coverage_df["after_gencore_depth"].isna()
                            | (coverage_df["after_gencore_depth"] < LOW_COVERAGE_THRESHOLD)
                        )
                    ]
                    if not low_coverage_samples.empty:
                        sample_text = ", ".join(
                            f"{row['sample_id']} ({format_metric(row['after_gencore_depth'])})"
                            for _, row in low_coverage_samples.iterrows()
                        )
                        st.warning(
                            f"Tumor variant coverage warning: one or more non-tumor samples are not adequately covered after gencore "
                            f"(< {LOW_COVERAGE_THRESHOLD}x or missing). Samples: {sample_text}"
                        )

                left, right = st.columns(2)
                with left:
                    st.subheader("Tumor Annovar Fields")
                    st.dataframe(load_variant_details(variant_row["tumor_row_json"]), width="stretch", hide_index=True)
                with right:
                    st.subheader("Tissue Annovar Fields")
                    st.dataframe(load_variant_details(variant_row["tissue_row_json"]), width="stretch", hide_index=True)

    with export_tab:
        if analyses.empty or analysis_row is None or selected_patient is None:
            st.info("No analyses were found in the dashboard database yet.")
        else:
            show_all_tissue_export = st.checkbox("Show all tissue variants", value=False, key="export_show_all_tissue")
            export_source_df = tissue_variants.copy() if show_all_tissue_export else tumor_pass.copy()
            export_title = "Export Tissue PASS Variants" if show_all_tissue_export else "Export Tumor PASS Variants"
            st.subheader(export_title)
            if export_source_df.empty:
                st.info(f"{export_title} table is not available yet. Refresh the dashboard database with the latest refresh script.")
            else:
                export_scope = st.selectbox("Export scope", ["Current analysis", "Current patient", "All analyses"])
                export_df = export_source_df
                if export_scope == "Current analysis":
                    export_df = export_df[
                        (export_df["patient_id"] == selected_patient)
                        & (export_df["tissue_sample_id"] == analysis_row["tissue_sample_id"])
                    ]
                elif export_scope == "Current patient":
                    export_df = export_df[export_df["patient_id"] == selected_patient]
                else:
                    selected_patients = st.multiselect("Patients", patient_ids, default=patient_ids)
                    if selected_patients:
                        export_df = export_df[export_df["patient_id"].isin(selected_patients)]

                tissue_options = sorted(export_df["tissue_sample_id"].dropna().unique().tolist())
                selected_tissues = st.multiselect("Tissue samples", tissue_options, default=tissue_options)
                if selected_tissues:
                    export_df = export_df[export_df["tissue_sample_id"].isin(selected_tissues)]

                gene_filter = st.text_input("Gene contains")
                if gene_filter.strip():
                    export_df = export_df[export_df["gene"].fillna("").str.contains(gene_filter.strip(), case=False, na=False)]

                if show_all_tissue_export:
                    only_matched = st.checkbox("Only variants matched in tumor", value=False)
                    if only_matched:
                        export_df = export_df[export_df["matched_in_tumor"].fillna(False)]
                    available_export_columns = [
                        "patient_id",
                        "blood_sample_id",
                        "tumor_sample_id",
                        "tissue_sample_id",
                        "variant_key",
                        "chrom",
                        "pos",
                        "ref",
                        "alt",
                        "gene",
                        "hgvs",
                        "clinvar",
                        "dbsnp",
                        "cosmic",
                        "intervar",
                        "tissue_af",
                        "tissue_dp",
                        "matched_in_tumor",
                        "tumor_af",
                        "tumor_dp",
                        "tumor_gene",
                        "tumor_hgvs",
                        "tissue_filter",
                        "tumor_filter",
                    ]
                    default_export_columns = [
                        "patient_id",
                        "tissue_sample_id",
                        "variant_key",
                        "gene",
                        "hgvs",
                        "clinvar",
                        "tissue_af",
                        "tissue_dp",
                        "matched_in_tumor",
                        "tumor_af",
                        "tumor_dp",
                    ]
                else:
                    only_matched = st.checkbox("Only variants matched in tissue", value=False)
                    if only_matched:
                        export_df = export_df[export_df["matched_in_tissue"].fillna(False)]
                    available_export_columns = [
                        "patient_id",
                        "blood_sample_id",
                        "tumor_sample_id",
                        "tissue_sample_id",
                        "variant_key",
                        "chrom",
                        "pos",
                        "ref",
                        "alt",
                        "gene",
                        "hgvs",
                        "clinvar",
                        "dbsnp",
                        "cosmic",
                        "intervar",
                        "tumor_af",
                        "tumor_dp",
                        "matched_in_tissue",
                        "tissue_af",
                        "tissue_dp",
                        "tissue_gene",
                        "tissue_hgvs",
                        "tumor_filter",
                        "tissue_filter",
                    ]
                    default_export_columns = [
                        "patient_id",
                        "tumor_sample_id",
                        "tissue_sample_id",
                        "variant_key",
                        "gene",
                        "hgvs",
                        "clinvar",
                        "tumor_af",
                        "tumor_dp",
                        "matched_in_tissue",
                        "tissue_af",
                        "tissue_dp",
                    ]
                selected_columns = st.multiselect(
                    "Columns to export",
                    available_export_columns,
                    default=default_export_columns,
                )
                if selected_columns:
                    preview_df = export_df[selected_columns].copy()
                    st.dataframe(preview_df, width="stretch", hide_index=True)
                    st.download_button(
                        label="Download CSV",
                        data=preview_df.to_csv(index=False).encode("utf-8"),
                        file_name=build_download_filename(export_scope, selected_patient, analysis_row["tissue_sample_id"]),
                        mime="text/csv",
                    )
                else:
                    st.warning("Select at least one column to export.")

    with alignment_tab:
        st.subheader("Alignment Viewer")
        selected_alignment = st.session_state.alignment_variant
        if not selected_alignment:
            st.info("Select a variant in Patient Explorer and click 'View in BAM' to inspect it here.")
        else:
            st.write(f"Variant: `{selected_alignment['variant_key']}`")

            flank_size = st.number_input("Viewer window half-size (bp)", min_value=5, max_value=100, value=15, step=5)
            show_blood_track = st.checkbox("Show blood BAM", value=st.session_state.alignment_show_blood)
            st.session_state.alignment_show_blood = show_blood_track

            if st.button("Load Viewer", key="load_alignment_viewer"):
                st.session_state.alignment_render_requested = True

            locus_start = max(1, int(selected_alignment["pos"]) - int(flank_size))
            locus_end = int(selected_alignment["pos"]) + int(flank_size)
            locus = f"{selected_alignment['chrom']}:{locus_start}-{locus_end}"
            st.write(f"Locus: `{locus}`")

            sample_ids = [
                selected_alignment["tumor_sample_id"],
                selected_alignment["tissue_sample_id_full"],
            ]
            if show_blood_track:
                sample_ids.insert(0, selected_alignment["blood_sample_id"])
            viewer_samples = samples[samples["sample_id"].isin(sample_ids)].copy()
            viewer_samples = viewer_samples.dropna(subset=["bam_relpath", "bai_relpath"])
            viewer_samples["sample_id"] = pd.Categorical(viewer_samples["sample_id"], categories=sample_ids, ordered=True)
            viewer_samples = viewer_samples.sort_values("sample_id")

            if viewer_samples.empty:
                st.error("No BAM/BAM index paths were found for the selected samples. Refresh the database with the latest refresh script.")
            else:
                tracks = []
                for _, row in viewer_samples.iterrows():
                    if not row["bam_relpath"] or not row["bai_relpath"]:
                        continue
                    tracks.append({
                        "name": f"{row['sample_id']} ({row['sample_group']})",
                        "type": "alignment",
                        "format": "bam",
                        "url": build_file_url(data_base_url, str(row["bam_relpath"])),
                        "indexURL": build_file_url(data_base_url, str(row["bai_relpath"])),
                        "height": 140,
                        "displayMode": "EXPANDED",
                        "alignmentRowHeight": 12,
                        "showCoverage": True,
                        "showMismatches": True,
                        "samplingWindowSize": 50,
                        "samplingDepth": 30,
                    })

                if not tracks:
                    st.error("The selected samples do not have accessible BAM/BAM index files for the viewer.")
                else:
                    track_table = pd.DataFrame([
                        {
                            "sample": track["name"],
                            "bam_url": track["url"],
                            "bai_url": track["indexURL"],
                        }
                        for track in tracks
                    ])
                    with st.expander("Track URLs"):
                        st.dataframe(track_table, width="stretch", hide_index=True)

                    if not st.session_state.alignment_render_requested:
                        st.info("Click Load Viewer to render the BAM tracks. This avoids reloading IGV on every Streamlit rerun.")
                    else:
                        render_igv_browser(igv_js_path, locus, tracks)
                        st.caption("The IGV viewer shows expanded reads, coverage, and mismatches, while still keeping a reduced sampling depth. If it feels slow, leave blood unchecked or reduce the bp window further.")


if __name__ == "__main__":
    main()
