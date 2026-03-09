from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import duckdb
import pandas as pd

SAMPLE_RE = re.compile(r"^(?P<patient>\d+)(?P<sample_type>[A-Za-z]+)(?P<replicate>\d*)$")
FLAGSTAT_TOTAL_RE = re.compile(r"^\s*(\d+)\s+\+\s+\d+\s+in total")
FLAGSTAT_MAPPED_RE = re.compile(r"^\s*(\d+)\s+\+\s+\d+\s+mapped\s+\(([^%]+)%")

SAMPLE_COLUMNS = [
    "sample_id",
    "patient_id",
    "sample_type_code",
    "sample_group",
    "sample_dir",
    "stats_dir",
    "sterr_dir",
    "fastp_json",
    "flagstat_txt",
    "flagstat_err",
    "mosdepth_before_summary_txt",
    "mosdepth_after_summary_txt",
    "before_per_base_bed_gz",
    "after_per_base_bed_gz",
    "bam_path",
    "bai_path",
    "bam_relpath",
    "bai_relpath",
    "fastp_total_reads",
    "fastp_passed_reads",
    "flagstat_total_reads",
    "flagstat_mapped_reads",
    "flagstat_mapped_pct",
    "mean_coverage_before_gencore",
    "mean_coverage_after_gencore",
]

ANALYSIS_COLUMNS = [
    "patient_id",
    "blood_sample_id",
    "tumor_sample_id",
    "tissue_sample_id",
    "analysis_dir",
    "tumor_annotation_csv",
    "tissue_pass_annotation_csv",
    "tissue_annotation_csv",
    "tumor_filtered_vcf",
    "tumor_pass_vcf",
    "tissue_filtered_vcf",
    "tissue_pass_vcf",
    "tissue_recovered_vcf",
    "tumor_detected_variants",
    "tumor_pass_variants",
    "tissue_detected_variants",
    "tissue_pass_variants",
    "tissue_recovered_variants",
]

RECOVERED_COLUMNS = [
    "patient_id",
    "blood_sample_id",
    "tumor_sample_id",
    "tissue_sample_id",
    "analysis_dir",
    "variant_key",
    "chrom",
    "pos",
    "end",
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
    "tissue_af",
    "tissue_dp",
    "tumor_filter",
    "tissue_filter",
    "recovered_in_tissue",
    "warning_shared_variant",
    "tumor_row_json",
    "tissue_row_json",
]

TUMOR_PASS_COLUMNS = [
    "patient_id",
    "blood_sample_id",
    "tumor_sample_id",
    "tissue_sample_id",
    "analysis_dir",
    "variant_key",
    "chrom",
    "pos",
    "end",
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
    "tumor_row_json",
    "tissue_row_json",
]

TISSUE_VARIANT_COLUMNS = [
    "patient_id",
    "blood_sample_id",
    "tumor_sample_id",
    "tissue_sample_id",
    "analysis_dir",
    "variant_key",
    "chrom",
    "pos",
    "end",
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
    "tissue_row_json",
    "tumor_row_json",
]

WARNING_COLUMNS = [
    "warning_type",
    "scope",
    "patient_id",
    "sample_id",
    "tissue_sample_id",
    "details",
]


@dataclass
class ParsedSample:
    sample_id: str
    patient_id: str
    sample_type_code: str
    sample_group: str


@dataclass
class SampleRecord:
    sample_id: str
    patient_id: str
    sample_type_code: str
    sample_group: str
    sample_dir: str
    stats_dir: str
    sterr_dir: str
    fastp_json: str
    flagstat_txt: str
    flagstat_err: str
    mosdepth_before_summary_txt: str
    mosdepth_after_summary_txt: str
    before_per_base_bed_gz: str
    after_per_base_bed_gz: str
    bam_path: str
    bai_path: str
    bam_relpath: str
    bai_relpath: str
    fastp_total_reads: Optional[int]
    fastp_passed_reads: Optional[int]
    flagstat_total_reads: Optional[int]
    flagstat_mapped_reads: Optional[int]
    flagstat_mapped_pct: Optional[float]
    mean_coverage_before_gencore: Optional[float]
    mean_coverage_after_gencore: Optional[float]


@dataclass
class AnalysisRecord:
    patient_id: str
    blood_sample_id: str
    tumor_sample_id: str
    tissue_sample_id: str
    analysis_dir: str
    tumor_annotation_csv: str
    tissue_pass_annotation_csv: str
    tissue_annotation_csv: str
    tumor_filtered_vcf: str
    tumor_pass_vcf: str
    tissue_filtered_vcf: str
    tissue_pass_vcf: str
    tissue_recovered_vcf: str
    tumor_detected_variants: Optional[int]
    tumor_pass_variants: Optional[int]
    tissue_detected_variants: Optional[int]
    tissue_pass_variants: Optional[int]
    tissue_recovered_variants: Optional[int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh the local dashboard database from synced pipeline outputs.")
    parser.add_argument("--results-root", required=True, help="Root directory containing synced pipeline outputs.")
    parser.add_argument("--db-path", required=True, help="DuckDB file to create or update.")
    return parser.parse_args()


def parse_sample_id(sample_id: str) -> Optional[ParsedSample]:
    prefix = sample_id.split("_")[0]
    match = SAMPLE_RE.match(prefix)
    if not match:
        return None

    sample_type_code = match.group("sample_type").lower()
    if sample_type_code == "b":
        sample_group = "blood"
    elif sample_type_code == "c":
        sample_group = "tumor"
    elif sample_type_code == "n":
        sample_group = "tissue"
    else:
        sample_group = "other"

    return ParsedSample(
        sample_id=sample_id,
        patient_id=match.group("patient"),
        sample_type_code=sample_type_code,
        sample_group=sample_group,
    )


def path_or_empty(path: Optional[Path]) -> str:
    return str(path) if path else ""


def relpath_or_empty(path: Optional[Path], root: Path) -> str:
    if not path:
        return ""
    return path.resolve().relative_to(root.resolve()).as_posix()


def find_first(base: Path, pattern: str, recursive: bool = False) -> Optional[Path]:
    if not base.exists():
        return None
    matches = sorted(base.rglob(pattern) if recursive else base.glob(pattern))
    return matches[0] if matches else None


def find_first_of(base: Path, patterns: list[str], recursive: bool = False) -> Optional[Path]:
    for pattern in patterns:
        match = find_first(base, pattern, recursive=recursive)
        if match:
            return match
    return None


def parse_fastp_json(path: Optional[Path]) -> tuple[Optional[int], Optional[int]]:
    if not path or not path.exists():
        return None, None

    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None, None

    summary = payload.get("summary", {})
    before = summary.get("before_filtering", {})
    after = summary.get("after_filtering", {})
    return before.get("total_reads"), after.get("total_reads")


def parse_flagstat(paths: list[Optional[Path]]) -> tuple[Optional[int], Optional[int], Optional[float]]:
    for path in paths:
        if not path or not path.exists() or path.stat().st_size == 0:
            continue

        total_reads = None
        mapped_reads = None
        mapped_pct = None
        try:
            for raw_line in path.read_text().splitlines():
                line = raw_line.strip()
                total_match = FLAGSTAT_TOTAL_RE.match(line)
                if total_match and total_reads is None:
                    total_reads = int(total_match.group(1))
                    continue

                mapped_match = FLAGSTAT_MAPPED_RE.match(line)
                if mapped_match and mapped_reads is None:
                    mapped_reads = int(mapped_match.group(1))
                    mapped_pct = float(mapped_match.group(2).strip())

            if total_reads is not None or mapped_reads is not None:
                return total_reads, mapped_reads, mapped_pct
        except (OSError, ValueError):
            continue

    return None, None, None


def parse_mosdepth_summary(path: Optional[Path]) -> Optional[float]:
    if not path or not path.exists():
        return None

    total_region_mean = None
    total_mean = None
    try:
        with path.open() as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 4:
                    continue
                label = parts[0].lower()
                if label == "total_region":
                    total_region_mean = float(parts[3])
                elif label == "total":
                    total_mean = float(parts[3])
    except (OSError, ValueError):
        return None

    return total_region_mean if total_region_mean is not None else total_mean


def count_vcf_records(path: Path) -> Optional[int]:
    if not path.exists():
        return None

    opener = gzip.open if path.suffix == ".gz" else open
    count = 0
    try:
        with opener(path, "rt") as handle:
            for line in handle:
                if not line.startswith("#"):
                    count += 1
    except OSError:
        return None
    return count


def build_sample_records(results_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for child in sorted(results_root.iterdir()):
        if not child.is_dir():
            continue

        parsed = parse_sample_id(child.name)
        if not parsed:
            continue

        stats_dir = child / "stats"
        sterr_dir = child / "stout_sterr"
        fastp_json = find_first(child, "*_fastp.json")
        flagstat_txt = find_first(stats_dir, "*_view.txt")
        flagstat_err = find_first(sterr_dir, "*_flagstat.err")
        mosdepth_before_summary = find_first(stats_dir, "*_before_gencore.mosdepth.summary.txt")
        mosdepth_after_summary = find_first(stats_dir, "*_after_gencore.mosdepth.summary.txt")
        before_per_base_bed = find_first(stats_dir, "*_before_gencore.per-base.bed.gz")
        after_per_base_bed = find_first(stats_dir, "*_after_gencore.per-base.bed.gz")
        bam_path = find_first(child, "*_005_RG.bam", recursive=True)
        bai_path = find_first_of(child, ["*_005_RG.bam.bai", "*_005_RG.bai"], recursive=True)

        fastp_total, fastp_passed = parse_fastp_json(fastp_json)
        total_reads, mapped_reads, mapped_pct = parse_flagstat([flagstat_txt, flagstat_err])
        mean_cov_before = parse_mosdepth_summary(mosdepth_before_summary)
        mean_cov_after = parse_mosdepth_summary(mosdepth_after_summary)

        records.append(asdict(SampleRecord(
            sample_id=parsed.sample_id,
            patient_id=parsed.patient_id,
            sample_type_code=parsed.sample_type_code,
            sample_group=parsed.sample_group,
            sample_dir=str(child),
            stats_dir=str(stats_dir),
            sterr_dir=str(sterr_dir),
            fastp_json=path_or_empty(fastp_json),
            flagstat_txt=path_or_empty(flagstat_txt),
            flagstat_err=path_or_empty(flagstat_err),
            mosdepth_before_summary_txt=path_or_empty(mosdepth_before_summary),
            mosdepth_after_summary_txt=path_or_empty(mosdepth_after_summary),
            before_per_base_bed_gz=path_or_empty(before_per_base_bed),
            after_per_base_bed_gz=path_or_empty(after_per_base_bed),
            bam_path=path_or_empty(bam_path),
            bai_path=path_or_empty(bai_path),
            bam_relpath=relpath_or_empty(bam_path, results_root),
            bai_relpath=relpath_or_empty(bai_path, results_root),
            fastp_total_reads=fastp_total,
            fastp_passed_reads=fastp_passed,
            flagstat_total_reads=total_reads,
            flagstat_mapped_reads=mapped_reads,
            flagstat_mapped_pct=mapped_pct,
            mean_coverage_before_gencore=mean_cov_before,
            mean_coverage_after_gencore=mean_cov_after,
        )))

    return records


def infer_analyses_from_manifest(results_root: Path) -> list[tuple[str, str, str, str]]:
    manifest_path = results_root / "patient_triplets.tsv"
    analyses: list[tuple[str, str, str, str]] = []
    if not manifest_path.exists():
        return analyses

    with manifest_path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            analyses.append((row["patient"], row["blood"], row["tumor"], row["tissue"]))
    return analyses


def infer_analyses_from_layout(results_root: Path, sample_df: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    analyses: list[tuple[str, str, str, str]] = []
    if sample_df.empty:
        return analyses

    for patient_dir in sorted([path for path in results_root.iterdir() if path.is_dir() and path.name.isdigit()]):
        patient_id = patient_dir.name
        patient_samples = sample_df[sample_df["patient_id"] == patient_id]
        blood_samples = patient_samples[patient_samples["sample_group"] == "blood"]["sample_id"].tolist()
        tumor_samples = patient_samples[patient_samples["sample_group"] == "tumor"]["sample_id"].tolist()
        if len(blood_samples) != 1 or len(tumor_samples) != 1:
            continue

        for analysis_dir in sorted([path for path in patient_dir.iterdir() if path.is_dir()]):
            parsed = parse_sample_id(analysis_dir.name)
            if parsed and parsed.sample_group == "tissue":
                analyses.append((patient_id, blood_samples[0], tumor_samples[0], parsed.sample_id))

    return analyses


def build_analysis_records(results_root: Path, sample_df: pd.DataFrame) -> list[dict[str, Any]]:
    manifest_analyses = infer_analyses_from_manifest(results_root)
    analyses = manifest_analyses or infer_analyses_from_layout(results_root, sample_df)

    records: list[dict[str, Any]] = []
    for patient_id, blood_sample_id, tumor_sample_id, tissue_sample_id in analyses:
        analysis_dir = results_root / patient_id / tissue_sample_id
        tumor_dir = analysis_dir / "tumor"
        tissue_dir = analysis_dir / "tissue"

        tumor_annotation_csv = tumor_dir / f"{patient_id}_tumor_PASSonly_Annotated.hg38_multianno.csv"
        tissue_pass_annotation_csv = tissue_dir / f"{patient_id}_tissue_PASSonly_Annotated.hg38_multianno.csv"
        tissue_annotation_csv = tissue_dir / f"{patient_id}_tissue_onlyTumorPassVariants_Annotated.hg38_multianno.csv"
        tumor_filtered_vcf = tumor_dir / f"{patient_id}_tumor_TN_Filtered.vcf.gz"
        tumor_pass_vcf = tumor_dir / f"{patient_id}_tumor_PASSonly.vcf.gz"
        tissue_filtered_vcf = tissue_dir / f"{patient_id}_tissue_TN_Filtered.vcf.gz"
        tissue_pass_vcf = tissue_dir / f"{patient_id}_tissue_PASSonly.vcf.gz"
        tissue_recovered_vcf = tissue_dir / f"{patient_id}_tissue_onlyTumorPassVariants.vcf.gz"

        records.append(asdict(AnalysisRecord(
            patient_id=patient_id,
            blood_sample_id=blood_sample_id,
            tumor_sample_id=tumor_sample_id,
            tissue_sample_id=tissue_sample_id,
            analysis_dir=str(analysis_dir),
            tumor_annotation_csv=path_or_empty(tumor_annotation_csv if tumor_annotation_csv.exists() else None),
            tissue_pass_annotation_csv=path_or_empty(tissue_pass_annotation_csv if tissue_pass_annotation_csv.exists() else None),
            tissue_annotation_csv=path_or_empty(tissue_annotation_csv if tissue_annotation_csv.exists() else None),
            tumor_filtered_vcf=path_or_empty(tumor_filtered_vcf if tumor_filtered_vcf.exists() else None),
            tumor_pass_vcf=path_or_empty(tumor_pass_vcf if tumor_pass_vcf.exists() else None),
            tissue_filtered_vcf=path_or_empty(tissue_filtered_vcf if tissue_filtered_vcf.exists() else None),
            tissue_pass_vcf=path_or_empty(tissue_pass_vcf if tissue_pass_vcf.exists() else None),
            tissue_recovered_vcf=path_or_empty(tissue_recovered_vcf if tissue_recovered_vcf.exists() else None),
            tumor_detected_variants=count_vcf_records(tumor_filtered_vcf),
            tumor_pass_variants=count_vcf_records(tumor_pass_vcf),
            tissue_detected_variants=count_vcf_records(tissue_filtered_vcf),
            tissue_pass_variants=count_vcf_records(tissue_pass_vcf),
            tissue_recovered_variants=count_vcf_records(tissue_recovered_vcf),
        )))

    return records


def read_annovar_csv(path_str: str) -> pd.DataFrame:
    if not path_str:
        return pd.DataFrame()

    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path, dtype=str).fillna("")
    df.columns = [str(column).strip() for column in df.columns]
    required = ["Chr", "Start", "End", "Ref", "Alt"]
    if not all(column in df.columns for column in required):
        return pd.DataFrame()

    df["variant_key"] = (
        df["Chr"].astype(str)
        + ":"
        + df["Start"].astype(str)
        + ":"
        + df["Ref"].astype(str)
        + ">"
        + df["Alt"].astype(str)
    )
    return df


def pick_column(columns: list[str], exact_candidates: list[str], contains_candidates: list[str] | None = None) -> Optional[str]:
    lowered = {column.lower(): column for column in columns}
    for candidate in exact_candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]

    for candidate in contains_candidates or []:
        for column in columns:
            if candidate.lower() in column.lower():
                return column
    return None


def resolve_annovar_columns(df: pd.DataFrame) -> dict[str, Optional[str]]:
    columns = list(df.columns)
    return {
        "gene": pick_column(columns, ["Gene.refGene", "Gene.refGeneWithVer", "Gene"]),
        "hgvs": pick_column(columns, ["AAChange.refGene", "AAChange.refGeneWithVer", "GeneDetail.refGene"]),
        "clinvar": pick_column(columns, [], ["clinvar", "clnsig"]),
        "dbsnp": pick_column(columns, ["avsnp150", "avsnp151"]),
        "cosmic": pick_column(columns, [], ["cosmic"]),
        "intervar": pick_column(columns, [], ["intervar"]),
        "af": pick_column(columns, ["Allele Frequency", "AF", "VAF", "Tumor_AF", "Tissue_AF"], ["allele frequency", "vaf"]),
        "dp": pick_column(columns, ["DP", "Read Depth", "ReadDepth", "Read_Depth", "Depth"], ["read depth"]),
    }


def first_value(row: pd.Series, columns: list[Optional[str]]) -> str:
    for column in columns:
        if column and column in row.index:
            value = row[column]
            if pd.notna(value) and str(value).strip():
                return str(value)
    return ""


def parse_numeric_literal(value: Any) -> Optional[float]:
    if value is None:
        return None

    text = str(value).strip()
    if not text or text == ".":
        return None

    is_percent = text.endswith("%")
    text = text.replace(",", "").replace("%", "")
    try:
        numeric = float(text)
    except ValueError:
        return None

    if is_percent:
        numeric /= 100.0
    return numeric


def numeric_value(row: pd.Series, columns: list[Optional[str]]) -> Optional[float]:
    for column in columns:
        if column and column in row.index:
            numeric = parse_numeric_literal(row[column])
            if numeric is not None:
                return numeric
    return None


def validate_results(results_root: Path, sample_df: pd.DataFrame, analysis_df: pd.DataFrame) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    manifest_path = results_root / "patient_triplets.tsv"

    if sample_df.empty:
        warnings.append({
            "warning_type": "missing_samples",
            "scope": "results_root",
            "patient_id": "",
            "sample_id": "",
            "tissue_sample_id": "",
            "details": "No sample directories matching the expected naming pattern were found under the synced results root.",
        })
        return warnings

    sample_duplicates = sample_df[sample_df.duplicated(subset=["sample_id"], keep=False)]
    for sample_id in sorted(sample_duplicates["sample_id"].dropna().unique().tolist()):
        warnings.append({
            "warning_type": "duplicate_sample_id",
            "scope": "sample_directory",
            "patient_id": "",
            "sample_id": sample_id,
            "tissue_sample_id": "",
            "details": f"Sample ID `{sample_id}` appears more than once in the synced results tree.",
        })

    if not manifest_path.exists():
        warnings.append({
            "warning_type": "missing_manifest",
            "scope": "results_root",
            "patient_id": "",
            "sample_id": "",
            "tissue_sample_id": "",
            "details": "patient_triplets.tsv was not found. The dashboard fell back to inferring analyses from the directory layout.",
        })
        return warnings

    try:
        with manifest_path.open(newline="") as handle:
            manifest_df = pd.read_csv(handle, sep="\t", dtype=str).fillna("")
    except (OSError, pd.errors.ParserError):
        warnings.append({
            "warning_type": "manifest_parse_error",
            "scope": "manifest",
            "patient_id": "",
            "sample_id": "",
            "tissue_sample_id": "",
            "details": "patient_triplets.tsv could not be parsed.",
        })
        return warnings

    required_columns = {"patient", "blood", "tumor", "tissue"}
    if not required_columns.issubset(set(manifest_df.columns)):
        warnings.append({
            "warning_type": "manifest_missing_columns",
            "scope": "manifest",
            "patient_id": "",
            "sample_id": "",
            "tissue_sample_id": "",
            "details": "patient_triplets.tsv is missing one or more required columns: patient, blood, tumor, tissue.",
        })
        return warnings

    duplicate_rows = manifest_df[manifest_df.duplicated(subset=["patient", "blood", "tumor", "tissue"], keep=False)]
    for _, row in duplicate_rows.drop_duplicates(subset=["patient", "blood", "tumor", "tissue"]).iterrows():
        warnings.append({
            "warning_type": "duplicate_manifest_row",
            "scope": "manifest",
            "patient_id": row["patient"],
            "sample_id": "",
            "tissue_sample_id": row["tissue"],
            "details": f"Duplicate manifest row for patient `{row['patient']}`, blood `{row['blood']}`, tumor `{row['tumor']}`, tissue `{row['tissue']}`.",
        })

    duplicate_tissues = manifest_df[manifest_df.duplicated(subset=["patient", "tissue"], keep=False)]
    for _, row in duplicate_tissues.drop_duplicates(subset=["patient", "tissue"]).iterrows():
        warnings.append({
            "warning_type": "duplicate_patient_tissue",
            "scope": "manifest",
            "patient_id": row["patient"],
            "sample_id": "",
            "tissue_sample_id": row["tissue"],
            "details": f"Manifest contains multiple rows for patient `{row['patient']}` and tissue `{row['tissue']}`.",
        })

    sample_lookup = sample_df.set_index("sample_id")[["patient_id", "sample_group"]].to_dict("index")
    analysis_keys = {
        (str(row["patient_id"]), str(row["blood_sample_id"]), str(row["tumor_sample_id"]), str(row["tissue_sample_id"]))
        for _, row in analysis_df.iterrows()
    }

    for _, row in manifest_df.iterrows():
        patient_id = row["patient"]
        tissue_id = row["tissue"]
        for role, expected_group in [("blood", "blood"), ("tumor", "tumor"), ("tissue", "tissue")]:
            sample_id = row[role]
            sample_info = sample_lookup.get(sample_id)
            if sample_info is None:
                warnings.append({
                    "warning_type": "manifest_missing_sample",
                    "scope": "manifest",
                    "patient_id": patient_id,
                    "sample_id": sample_id,
                    "tissue_sample_id": tissue_id,
                    "details": f"Manifest references missing {role} sample `{sample_id}` for patient `{patient_id}`.",
                })
                continue

            if str(sample_info["patient_id"]) != patient_id:
                warnings.append({
                    "warning_type": "manifest_patient_mismatch",
                    "scope": "manifest",
                    "patient_id": patient_id,
                    "sample_id": sample_id,
                    "tissue_sample_id": tissue_id,
                    "details": f"Manifest patient `{patient_id}` does not match the patient parsed from sample `{sample_id}`.",
                })

            if str(sample_info["sample_group"]) != expected_group:
                warnings.append({
                    "warning_type": "manifest_sample_type_mismatch",
                    "scope": "manifest",
                    "patient_id": patient_id,
                    "sample_id": sample_id,
                    "tissue_sample_id": tissue_id,
                    "details": f"Sample `{sample_id}` is not recognized as a {expected_group} sample.",
                })

        analysis_key = (patient_id, row["blood"], row["tumor"], row["tissue"])
        if analysis_key not in analysis_keys:
            warnings.append({
                "warning_type": "missing_analysis_output",
                "scope": "analysis",
                "patient_id": patient_id,
                "sample_id": "",
                "tissue_sample_id": tissue_id,
                "details": f"No patient analysis directory or expected outputs were found for patient `{patient_id}` tissue `{tissue_id}`.",
            })

    return warnings


def build_recovered_variant_records(analysis_df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for analysis in analysis_df.to_dict(orient="records"):
        tumor_df = read_annovar_csv(analysis["tumor_annotation_csv"])
        tissue_df = read_annovar_csv(analysis["tissue_annotation_csv"])
        if tumor_df.empty or tissue_df.empty:
            continue

        tumor_cols = resolve_annovar_columns(tumor_df)
        tissue_cols = resolve_annovar_columns(tissue_df)
        tumor_rows = {row["variant_key"]: row for _, row in tumor_df.iterrows()}

        for _, tissue_row in tissue_df.iterrows():
            tumor_row = tumor_rows.get(tissue_row["variant_key"])
            if tumor_row is None:
                continue

            records.append({
                "patient_id": analysis["patient_id"],
                "blood_sample_id": analysis["blood_sample_id"],
                "tumor_sample_id": analysis["tumor_sample_id"],
                "tissue_sample_id": analysis["tissue_sample_id"],
                "analysis_dir": analysis["analysis_dir"],
                "variant_key": tissue_row["variant_key"],
                "chrom": str(tissue_row["Chr"]),
                "pos": int(float(tissue_row["Start"])),
                "end": int(float(tissue_row["End"])),
                "ref": str(tissue_row["Ref"]),
                "alt": str(tissue_row["Alt"]),
                "gene": first_value(tissue_row, [tissue_cols["gene"]]) or first_value(tumor_row, [tumor_cols["gene"]]),
                "hgvs": first_value(tissue_row, [tissue_cols["hgvs"]]) or first_value(tumor_row, [tumor_cols["hgvs"]]),
                "clinvar": first_value(tissue_row, [tissue_cols["clinvar"]]) or first_value(tumor_row, [tumor_cols["clinvar"]]),
                "dbsnp": first_value(tissue_row, [tissue_cols["dbsnp"]]) or first_value(tumor_row, [tumor_cols["dbsnp"]]),
                "cosmic": first_value(tissue_row, [tissue_cols["cosmic"]]) or first_value(tumor_row, [tumor_cols["cosmic"]]),
                "intervar": first_value(tissue_row, [tissue_cols["intervar"]]) or first_value(tumor_row, [tumor_cols["intervar"]]),
                "tumor_af": numeric_value(tumor_row, [tumor_cols["af"]]),
                "tumor_dp": numeric_value(tumor_row, [tumor_cols["dp"]]),
                "tissue_af": numeric_value(tissue_row, [tissue_cols["af"]]),
                "tissue_dp": numeric_value(tissue_row, [tissue_cols["dp"]]),
                "tumor_filter": "PASS",
                "tissue_filter": "PASS",
                "recovered_in_tissue": True,
                "warning_shared_variant": True,
                "tumor_row_json": json.dumps(tumor_row.to_dict(), ensure_ascii=True),
                "tissue_row_json": json.dumps(tissue_row.to_dict(), ensure_ascii=True),
            })

    return records


def build_tumor_pass_variant_records(analysis_df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for analysis in analysis_df.to_dict(orient="records"):
        tumor_df = read_annovar_csv(analysis["tumor_annotation_csv"])
        if tumor_df.empty:
            continue

        tissue_df = read_annovar_csv(analysis["tissue_annotation_csv"])
        tumor_cols = resolve_annovar_columns(tumor_df)
        tissue_cols = resolve_annovar_columns(tissue_df) if not tissue_df.empty else {}
        tissue_rows = {row["variant_key"]: row for _, row in tissue_df.iterrows()} if not tissue_df.empty else {}

        for _, tumor_row in tumor_df.iterrows():
            tissue_row = tissue_rows.get(tumor_row["variant_key"])
            matched = tissue_row is not None
            records.append({
                "patient_id": analysis["patient_id"],
                "blood_sample_id": analysis["blood_sample_id"],
                "tumor_sample_id": analysis["tumor_sample_id"],
                "tissue_sample_id": analysis["tissue_sample_id"],
                "analysis_dir": analysis["analysis_dir"],
                "variant_key": tumor_row["variant_key"],
                "chrom": str(tumor_row["Chr"]),
                "pos": int(float(tumor_row["Start"])),
                "end": int(float(tumor_row["End"])),
                "ref": str(tumor_row["Ref"]),
                "alt": str(tumor_row["Alt"]),
                "gene": first_value(tumor_row, [tumor_cols["gene"]]),
                "hgvs": first_value(tumor_row, [tumor_cols["hgvs"]]),
                "clinvar": first_value(tumor_row, [tumor_cols["clinvar"]]),
                "dbsnp": first_value(tumor_row, [tumor_cols["dbsnp"]]),
                "cosmic": first_value(tumor_row, [tumor_cols["cosmic"]]),
                "intervar": first_value(tumor_row, [tumor_cols["intervar"]]),
                "tumor_af": numeric_value(tumor_row, [tumor_cols["af"]]),
                "tumor_dp": numeric_value(tumor_row, [tumor_cols["dp"]]),
                "matched_in_tissue": matched,
                "tissue_af": numeric_value(tissue_row, [tissue_cols.get("af")]) if matched else None,
                "tissue_dp": numeric_value(tissue_row, [tissue_cols.get("dp")]) if matched else None,
                "tissue_gene": first_value(tissue_row, [tissue_cols.get("gene")]) if matched else "",
                "tissue_hgvs": first_value(tissue_row, [tissue_cols.get("hgvs")]) if matched else "",
                "tumor_filter": "PASS",
                "tissue_filter": "PASS" if matched else "",
                "tumor_row_json": json.dumps(tumor_row.to_dict(), ensure_ascii=True),
                "tissue_row_json": json.dumps(tissue_row.to_dict(), ensure_ascii=True) if matched else "",
            })

    return records


def build_tissue_variant_records(analysis_df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for analysis in analysis_df.to_dict(orient="records"):
        tissue_df = read_annovar_csv(analysis["tissue_pass_annotation_csv"])
        if tissue_df.empty:
            continue

        tumor_df = read_annovar_csv(analysis["tumor_annotation_csv"])
        tissue_cols = resolve_annovar_columns(tissue_df)
        tumor_cols = resolve_annovar_columns(tumor_df) if not tumor_df.empty else {}
        tumor_rows = {row["variant_key"]: row for _, row in tumor_df.iterrows()} if not tumor_df.empty else {}

        for _, tissue_row in tissue_df.iterrows():
            tumor_row = tumor_rows.get(tissue_row["variant_key"])
            matched = tumor_row is not None
            records.append({
                "patient_id": analysis["patient_id"],
                "blood_sample_id": analysis["blood_sample_id"],
                "tumor_sample_id": analysis["tumor_sample_id"],
                "tissue_sample_id": analysis["tissue_sample_id"],
                "analysis_dir": analysis["analysis_dir"],
                "variant_key": tissue_row["variant_key"],
                "chrom": str(tissue_row["Chr"]),
                "pos": int(float(tissue_row["Start"])),
                "end": int(float(tissue_row["End"])),
                "ref": str(tissue_row["Ref"]),
                "alt": str(tissue_row["Alt"]),
                "gene": first_value(tissue_row, [tissue_cols["gene"]]),
                "hgvs": first_value(tissue_row, [tissue_cols["hgvs"]]),
                "clinvar": first_value(tissue_row, [tissue_cols["clinvar"]]),
                "dbsnp": first_value(tissue_row, [tissue_cols["dbsnp"]]),
                "cosmic": first_value(tissue_row, [tissue_cols["cosmic"]]),
                "intervar": first_value(tissue_row, [tissue_cols["intervar"]]),
                "tissue_af": numeric_value(tissue_row, [tissue_cols["af"]]),
                "tissue_dp": numeric_value(tissue_row, [tissue_cols["dp"]]),
                "matched_in_tumor": matched,
                "tumor_af": numeric_value(tumor_row, [tumor_cols.get("af")]) if matched else None,
                "tumor_dp": numeric_value(tumor_row, [tumor_cols.get("dp")]) if matched else None,
                "tumor_gene": first_value(tumor_row, [tumor_cols.get("gene")]) if matched else "",
                "tumor_hgvs": first_value(tumor_row, [tumor_cols.get("hgvs")]) if matched else "",
                "tissue_filter": "PASS",
                "tumor_filter": "PASS" if matched else "",
                "tissue_row_json": json.dumps(tissue_row.to_dict(), ensure_ascii=True),
                "tumor_row_json": json.dumps(tumor_row.to_dict(), ensure_ascii=True) if matched else "",
            })

    return records


def dataframe_from_records(records: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame.from_records(records)
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[columns]


def main() -> None:
    args = parse_args()
    results_root = Path(args.results_root).expanduser().resolve()
    db_path = Path(args.db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    sample_records = build_sample_records(results_root)
    sample_df = dataframe_from_records(sample_records, SAMPLE_COLUMNS)

    analysis_records = build_analysis_records(results_root, sample_df)
    analysis_df = dataframe_from_records(analysis_records, ANALYSIS_COLUMNS)

    warning_records = validate_results(results_root, sample_df, analysis_df)
    warning_df = dataframe_from_records(warning_records, WARNING_COLUMNS)

    recovered_records = build_recovered_variant_records(analysis_df)
    recovered_df = dataframe_from_records(recovered_records, RECOVERED_COLUMNS)

    tumor_pass_records = build_tumor_pass_variant_records(analysis_df)
    tumor_pass_df = dataframe_from_records(tumor_pass_records, TUMOR_PASS_COLUMNS)

    tissue_variant_records = build_tissue_variant_records(analysis_df)
    tissue_variant_df = dataframe_from_records(tissue_variant_records, TISSUE_VARIANT_COLUMNS)

    con = duckdb.connect(str(db_path))
    con.register("sample_df", sample_df)
    con.execute("create or replace table sample_metrics as select * from sample_df")
    con.register("analysis_df", analysis_df)
    con.execute("create or replace table analysis_runs as select * from analysis_df")
    con.register("warning_df", warning_df)
    con.execute("create or replace table refresh_warnings as select * from warning_df")
    con.register("recovered_df", recovered_df)
    con.execute("create or replace table recovered_variants as select * from recovered_df")
    con.register("tumor_pass_df", tumor_pass_df)
    con.execute("create or replace table tumor_pass_variants as select * from tumor_pass_df")
    con.register("tissue_variant_df", tissue_variant_df)
    con.execute("create or replace table tissue_variants as select * from tissue_variant_df")
    con.execute(
        "create or replace table dashboard_metadata as select current_timestamp as refreshed_at, ? as results_root",
        [str(results_root)],
    )
    con.close()

    print(f"Refreshed dashboard database: {db_path}")
    print(f"Samples loaded: {len(sample_df)}")
    print(f"Analyses loaded: {len(analysis_df)}")
    print(f"Warnings loaded: {len(warning_df)}")
    print(f"Recovered variants loaded: {len(recovered_df)}")
    print(f"Tumor PASS variants loaded: {len(tumor_pass_df)}")
    print(f"Tissue PASS variants loaded: {len(tissue_variant_df)}")


if __name__ == "__main__":
    main()
