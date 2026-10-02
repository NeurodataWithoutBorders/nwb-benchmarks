import shutil
import textwrap
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import seaborn as sns
from packaging import version

from nwb_benchmarks.database._processing import (
    ENVIRONMENT_TIMEPOINTS,
    BenchmarkDatabase,
)

DEFAULT_BENCHMARK_LABELS = OrderedDict(
    [
        ("hdf5 h5py remfile no cache", "HDF5 remfile"),
        ("hdf5 h5py remfile with cache", "HDF5 remfile cache"),
        ("hdf5 h5py fsspec https no cache", "HDF5 fsspec HTTPS"),
        ("hdf5 h5py fsspec https with cache", "HDF5 fsspec HTTPS cache"),
        ("hdf5 h5py fsspec s3 no cache", "HDF5 fsspec S3"),
        ("hdf5 h5py fsspec s3 with cache", "HDF5 fsspec S3 cache"),
        ("hdf5 h5py ros3", "HDF5 ROS3"),
        ("lindi h5py", "LINDI"),
        ("zarr s3", "Zarr"),
        ("zarr s3 force no consolidated", "Zarr unconsol."),
    ]
)
DEFAULT_BENCHMARK_ORDER = list(DEFAULT_BENCHMARK_LABELS.keys())

NETWORK_METRIC_LABELS = {
    "amount_downloaded_in_bytes": "Downloaded bytes",
    "amount_downloaded_in_number_of_packets": "Downloaded packets",
    "amount_uploaded_in_bytes": "Uploaded bytes",
    "amount_uploaded_in_number_of_packets": "Uploaded packets",
    "mean_time_per_web_packet": "Mean time per web packet (s)",
    "network_total_time_in_seconds": "Network total time (s)",
    "total_traffic_in_number_of_web_packets": "Total web packets",
    "total_transfer_in_bytes": "Total transfer bytes",
    "total_transfer_in_number_of_packets": "Total transfer packets",
    "total_transfer_time_in_seconds": "Total transfer time (s)",
}


class BenchmarkVisualizer:
    """Handles plotting and visualization of benchmark results."""

    file_open_order = DEFAULT_BENCHMARK_ORDER
    pynwb_read_order = [
        method.replace("h5py", "pynwb").replace("zarr", "zarr pynwb") for method in DEFAULT_BENCHMARK_ORDER
    ]
    download_order = ["hdf5 dandi api", "zarr dandi api", "lindi dandi api"]
    # TODO - where does lindi local json value go / what should it be called

    def __init__(self, output_directory: Optional[Path] = None, summary_tables_directory: Optional[Path] = None):
        """Initialize visualizer with output directory.

        Args:
            output_directory: Directory for saving figures
            summary_tables_directory: Directory for optional CSV summary tables. If not provided, no summary tables
                are written.
        """
        self.output_directory = output_directory or Path(__file__).parent / "figures"
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.summary_tables_directory = Path(summary_tables_directory) if summary_tables_directory is not None else None
        if self.summary_tables_directory is not None:
            self.summary_tables_directory.mkdir(parents=True, exist_ok=True)
        self._base_output_directory = self.output_directory
        self._base_summary_tables_directory = self.summary_tables_directory
        self.environment_label = None
        self.environment_filename_postfix = ""
        self.environment_caption_dates = None
        self.skipped_outputs = []
        self._setup_matplotlib()

    @staticmethod
    def _environment_subdirectory_name(environment_label: str) -> str:
        """Return output subdirectory for an environment plotting context."""
        return "environments_all" if environment_label == "all" else f"environment_date_{environment_label}"

    def _set_environment_output_context(
        self, environment_label: Optional[str], environment_caption_dates: Optional[List[str]] = None
    ) -> None:
        """Set output directories and filename postfix for the current plotting context."""
        self.environment_label = environment_label
        self.environment_caption_dates = environment_caption_dates
        self.environment_filename_postfix = "" if environment_label is None else f"_{environment_label}"

        if environment_label is None:
            self.output_directory = self._base_output_directory
            self.summary_tables_directory = self._base_summary_tables_directory
            return

        subdirectory_name = self._environment_subdirectory_name(environment_label)
        self.output_directory = self._base_output_directory / subdirectory_name
        self.output_directory.mkdir(parents=True, exist_ok=True)
        if self._base_summary_tables_directory is not None:
            self.summary_tables_directory = self._base_summary_tables_directory / subdirectory_name
            self.summary_tables_directory.mkdir(parents=True, exist_ok=True)

    def _add_environment_caption(self, caption: Optional[str]) -> Optional[str]:
        """Append environment-date context to captions for non-performance-over-time plots."""
        if caption is None or self.environment_label is None:
            return caption
        if self.environment_label == "all":
            dates = ", ".join(self.environment_caption_dates or [])
            return caption + f"Environment dates included: {dates}. "
        return caption + f"Environment date included: {self.environment_label}. "

    def _filename_with_environment_postfix(self, stem: str, suffix: str = "", extension: str = ".pdf") -> str:
        """Build a filename that includes the active environment postfix."""
        return f"{stem}{suffix}{self.environment_filename_postfix}{extension}"

    def _record_skipped_output(self, output_type: str, filename: Path | str, reason: str) -> None:
        """Record a skipped figure or table for the root-level skipped-output report."""
        self.skipped_outputs.append(
            {
                "environment": self.environment_label or "root",
                "type": output_type,
                "filename": str(filename),
                "reason": reason,
            }
        )

    def _write_skipped_outputs_report(self) -> None:
        """Write a root-level text report describing skipped figures and summary tables."""
        report_path = self._base_output_directory / "skipped_outputs.txt"
        if not self.skipped_outputs:
            report_path.write_text("No plots or summary tables were skipped.\n")
            return

        lines = [
            "Skipped benchmark figure-generation outputs",
            "===========================================",
            "",
            "The following plots or summary tables were skipped during figure generation.",
            "",
        ]
        for skipped_output in self.skipped_outputs:
            lines.extend(
                [
                    f"Environment: {skipped_output['environment']}",
                    f"Type: {skipped_output['type']}",
                    f"Output: {skipped_output['filename']}",
                    f"Reason: {skipped_output['reason']}",
                    "",
                ]
            )
        report_path.write_text("\n".join(lines))

    @staticmethod
    def _setup_matplotlib():
        """Setup matplotlib settings for editable text in Illustrator."""
        matplotlib.rcParams["pdf.fonttype"] = 42
        matplotlib.rcParams["ps.fonttype"] = 42
        matplotlib.rcParams["font.family"] = "Arial"

    @staticmethod
    def _format_stat_text(mean: float, std: float, count: int) -> str:
        """Format statistical text based on value magnitude."""
        if mean > 1000 or mean < 0.01:
            return f"  {mean:.2e} ± {std:.2e}, n={int(count)}"
        return f"  {mean:.2f} ± {std:.2f}, n={int(count)}"

    @staticmethod
    def _safe_median(series: pd.Series) -> float:
        """Return the median of non-null values, or NaN for empty/all-null series without warning."""
        non_null = series.dropna()
        if non_null.empty:
            return np.nan
        return non_null.median()

    def _add_mean_std_annotations(self, value: str, group: str, order: List[str], **kwargs):
        """Add mean ± std annotations to plot."""
        data = kwargs.get("data")
        stats_data = data[[group, value]].dropna(subset=[value])
        if stats_data.empty:
            return
        stats_df = stats_data.groupby(group, observed=True)[value].agg(["mean", "std", "max", "count"])

        for i, label in enumerate(order):
            if label in stats_df.index:
                stats = stats_df.loc[label, :]
                mean_sem_text = self._format_stat_text(stats["mean"], stats["std"], stats["count"])

                plt.text(
                    x=stats["max"],
                    y=i,
                    s=mean_sem_text,
                    verticalalignment="center",
                    horizontalalignment="left",
                    fontsize=8,
                )

    def _get_filename_prefix(self, network_tracking: bool) -> str:
        """Get filename prefix based on network tracking."""
        return "network_tracking_" if network_tracking else ""

    def _create_plot_kwargs(
        self, df, group: str, order: List[str], filename: Path, kind: str = "box", **extra_kwargs
    ) -> Dict[str, Any]:
        """Create common plot kwargs to reduce duplication."""
        plot_kwargs = {
            "df": df,
            "group": group,
            "metric_order": order,
            "filename": filename,
            "kind": kind,
        }

        if kind == "box":
            plot_kwargs["catplot_kwargs"] = {"showfliers": False, "boxprops": dict(linewidth=0)}

        plot_kwargs.update(extra_kwargs)

        return plot_kwargs

    @staticmethod
    def _display_method_labels(method_order: List[str]) -> List[str]:
        """Return display labels for backend and PyNWB benchmark method names."""
        display_labels = dict(DEFAULT_BENCHMARK_LABELS)
        display_labels.update(
            {
                method.replace("h5py", "pynwb").replace("zarr", "zarr pynwb"): label
                for method, label in DEFAULT_BENCHMARK_LABELS.items()
            }
        )
        labels = [display_labels.get(method, method) for method in method_order]
        return labels

    @staticmethod
    def _display_method_label(method: str) -> str:
        """Return display label for one backend or PyNWB benchmark method name."""
        label = BenchmarkVisualizer._display_method_labels([method])[0]
        return label

    def _write_summary_table(
        self,
        df: pd.DataFrame,
        group_cols: List[str],
        value_col: str,
        filename: str,
    ) -> None:
        """Write a grouped CSV summary table if summary table output is enabled."""
        if self.summary_tables_directory is None:
            return

        if df.empty:
            self._record_skipped_output("summary table", filename, "No data available for summary table.")
            return

        missing_cols = [col for col in [*group_cols, value_col] if col not in df.columns]
        if missing_cols:
            self._record_skipped_output("summary table", filename, f"Missing columns: {missing_cols}.")
            return

        summary_df = (
            df.groupby(group_cols, dropna=False)[value_col]
            .agg(n="count", mean="mean", median="median", std="std", min="min", max="max")
            .reset_index()
        )
        summary_df.to_csv(self.summary_tables_directory / filename, index=False)

    def copy_environment_details(
        self, db: BenchmarkDatabase, environment_timepoints: Optional[Dict[str, str]] = None
    ) -> None:
        """Copy configured environment JSON files to the summary-table output directory."""
        if self.summary_tables_directory is None:
            return

        environment_timepoints = environment_timepoints or ENVIRONMENT_TIMEPOINTS
        environment_directory = db.results_directory / "environments"
        for environment_date, environment_id in environment_timepoints.items():
            source_path = environment_directory / f"environment-{environment_id}.json"
            target_path = self.summary_tables_directory / f"environment_date_{environment_date}.json"
            if not source_path.exists():
                self._record_skipped_output(
                    "environment details", target_path.name, f"Missing environment file: {source_path}."
                )
                continue
            shutil.copy2(source_path, target_path)

    @staticmethod
    def _environment_date_map() -> Dict[str, str]:
        """Return mapping from configured environment IDs to date labels."""
        return {environment_id: environment_date for environment_date, environment_id in ENVIRONMENT_TIMEPOINTS.items()}

    @staticmethod
    def _benchmark_family(benchmark_name_type: str, benchmark_name_clean: str) -> Optional[str]:
        """Map ordinary and network-tracking benchmark rows to comparable benchmark families."""
        if benchmark_name_type in ["time_remote_file_reading", "network_tracking_remote_file_reading"]:
            if "pynwb" in str(benchmark_name_clean):
                return "remote_file_reading_pynwb"
            return "remote_file_opening_backend"
        family_map = {
            "time_remote_slicing": "remote_slicing",
            "network_tracking_remote_slicing": "remote_slicing",
        }
        return family_map.get(benchmark_name_type)

    @staticmethod
    def _safe_correlation(df: pd.DataFrame, x_col: str, y_col: str, method: str) -> float:
        """Compute a correlation, returning NaN when it is undefined."""
        if len(df) < 3 or df[x_col].nunique(dropna=True) < 2 or df[y_col].nunique(dropna=True) < 2:
            return np.nan
        return df[x_col].corr(df[y_col], method=method)

    def _build_network_runtime_matched_table(self, db: BenchmarkDatabase) -> pd.DataFrame:
        """Build environment-aware matched ordinary-runtime and network-metric condition table."""
        df = db.get_results().collect().to_pandas()
        if df.empty:
            return pd.DataFrame()

        df = df.copy()
        df["environment_date"] = df["environment_id"].map(self._environment_date_map())
        df["benchmark_family"] = df.apply(
            lambda row: self._benchmark_family(row["benchmark_name_type"], row["benchmark_name_clean"]), axis=1
        )
        df = df[df["benchmark_family"].notna() & df["environment_date"].notna()]

        key_cols = [
            "environment_id",
            "environment_date",
            "benchmark_family",
            "modality",
            "benchmark_name_clean",
            "is_preloaded",
            "slice_number",
            "scaling_value",
        ]
        ordinary = df[df["benchmark_name_type"].isin(["time_remote_file_reading", "time_remote_slicing"])]
        ordinary = (
            ordinary.groupby(key_cols, dropna=False)["value"]
            .agg(ordinary_runtime_n="count", ordinary_runtime_median="median", ordinary_runtime_mean="mean")
            .reset_index()
        )

        network = df[
            df["benchmark_name_type"].isin(["network_tracking_remote_file_reading", "network_tracking_remote_slicing"])
        ]
        network = (
            network.groupby([*key_cols, "variable"], dropna=False)["value"]
            .agg(network_metric_n="count", network_metric_median="median", network_metric_mean="mean")
            .reset_index()
        )
        network_median = network.pivot_table(
            index=key_cols, columns="variable", values="network_metric_median", aggfunc="first", dropna=False
        ).reset_index()
        network_mean = network.pivot_table(
            index=key_cols, columns="variable", values="network_metric_mean", aggfunc="first", dropna=False
        ).reset_index()
        network_mean = network_mean.rename(
            columns={col: f"{col}_mean" for col in network_mean.columns if col not in key_cols}
        )
        network_n = network.pivot_table(
            index=key_cols, columns="variable", values="network_metric_n", aggfunc="first", dropna=False
        ).reset_index()
        network_n = network_n.rename(columns={col: f"{col}_n" for col in network_n.columns if col not in key_cols})

        matched = ordinary.merge(network_median, on=key_cols, how="inner")
        matched = matched.merge(network_mean, on=key_cols, how="left").merge(network_n, on=key_cols, how="left")
        return matched.sort_values(
            [
                "environment_date",
                "benchmark_family",
                "modality",
                "is_preloaded",
                "slice_number",
                "benchmark_name_clean",
            ],
            na_position="first",
        )

    def _compute_network_runtime_correlations(
        self, matched_df: pd.DataFrame, metrics: List[str], group_cols: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """Compute Spearman and Pearson correlations for matched network/runtime evidence."""
        group_cols = group_cols or []
        rows = []
        grouped = [((), matched_df)] if not group_cols else matched_df.groupby(group_cols, dropna=False)
        for group_key, group_df in grouped:
            if group_cols and not isinstance(group_key, tuple):
                group_key = (group_key,)
            group_values = dict(zip(group_cols, group_key)) if group_cols else {}
            for metric in metrics:
                if metric not in group_df.columns:
                    continue
                corr_df = group_df[["ordinary_runtime_median", metric]].dropna()
                rows.append(
                    {
                        **group_values,
                        "network_metric": metric,
                        "network_metric_label": NETWORK_METRIC_LABELS.get(metric, metric),
                        "n": len(corr_df),
                        "spearman_r": self._safe_correlation(corr_df, "ordinary_runtime_median", metric, "spearman"),
                        "pearson_r": self._safe_correlation(corr_df, "ordinary_runtime_median", metric, "pearson"),
                    }
                )
        return pd.DataFrame(rows)

    def _compute_network_runtime_pooled_correlations_by_modality(
        self, matched_df: pd.DataFrame, metrics: List[str]
    ) -> pd.DataFrame:
        """Compute pooled correlations by benchmark family for all data and each modality."""
        rows = []
        for modality_group, modality_df in [("all", matched_df), *list(matched_df.groupby("modality", dropna=False))]:
            if pd.isna(modality_group):
                modality_group = "unknown"
            correlations = self._compute_network_runtime_correlations(modality_df, metrics, ["benchmark_family"])
            correlations["modality_group"] = modality_group
            rows.append(correlations)
        if not rows:
            return pd.DataFrame()
        pooled = pd.concat(rows, ignore_index=True)
        modality_order = ["all", "Ecephys", "Ophys", "Icephys", "unknown"]
        pooled["modality_group"] = pd.Categorical(pooled["modality_group"], categories=modality_order, ordered=True)
        return pooled.sort_values(["benchmark_family", "modality_group", "network_metric"])

    @staticmethod
    def _cache_stack_from_benchmark_name(benchmark_name: str) -> Optional[str]:
        """Identify cache-comparable access stacks from cleaned benchmark names."""
        if "fsspec https" in benchmark_name:
            return "fsspec_https"
        if "fsspec s3" in benchmark_name:
            return "fsspec_s3"
        if "remfile" in benchmark_name:
            return "remfile"
        return None

    @staticmethod
    def _cache_state_from_benchmark_name(benchmark_name: str) -> Optional[str]:
        """Identify whether a cleaned benchmark name is a with-cache or no-cache variant."""
        if "with cache" in benchmark_name:
            return "with_cache"
        if "no cache" in benchmark_name:
            return "no_cache"
        return None

    def _build_cache_effect_pair_table(self, matched_df: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
        """Build environment-aware with-cache vs no-cache paired summaries from matched conditions."""
        cache_df = matched_df.copy()
        cache_df["cache_stack"] = cache_df["benchmark_name_clean"].map(self._cache_stack_from_benchmark_name)
        cache_df["cache_state"] = cache_df["benchmark_name_clean"].map(self._cache_state_from_benchmark_name)
        cache_df["cache_pair_name"] = (
            cache_df["benchmark_name_clean"]
            .str.replace(" with cache", "", regex=False)
            .str.replace(" no cache", "", regex=False)
        )
        cache_df = cache_df[cache_df["cache_stack"].notna() & cache_df["cache_state"].isin(["with_cache", "no_cache"])]
        if cache_df.empty:
            return pd.DataFrame()
        cache_df["slice_number"] = cache_df["slice_number"].fillna("not_applicable")
        cache_df["scaling_value"] = cache_df["scaling_value"].fillna("not_applicable")

        value_cols = ["ordinary_runtime_median", *metrics]
        id_cols = [
            "environment_id",
            "environment_date",
            "benchmark_family",
            "modality",
            "cache_stack",
            "cache_pair_name",
            "is_preloaded",
            "slice_number",
            "scaling_value",
        ]
        paired = cache_df.pivot_table(
            index=id_cols,
            columns="cache_state",
            values=value_cols,
            aggfunc="first",
            dropna=True,
        )
        paired.columns = [f"{value_col}_{cache_state}" for value_col, cache_state in paired.columns]
        paired = paired.reset_index()
        paired["slice_number"] = paired["slice_number"].where(paired["slice_number"] != "not_applicable", np.nan)
        paired["scaling_value"] = paired["scaling_value"].where(paired["scaling_value"] != "not_applicable", np.nan)

        required_cols = ["ordinary_runtime_median_no_cache", "ordinary_runtime_median_with_cache"]
        paired = paired.dropna(subset=required_cols, how="any")
        for value_col in value_cols:
            no_cache_col = f"{value_col}_no_cache"
            with_cache_col = f"{value_col}_with_cache"
            if no_cache_col not in paired.columns or with_cache_col not in paired.columns:
                continue
            paired[f"{value_col}_delta_with_minus_no_cache"] = paired[with_cache_col] - paired[no_cache_col]
            paired[f"{value_col}_ratio_with_over_no_cache"] = paired[with_cache_col] / paired[no_cache_col].replace(
                0, np.nan
            )
            paired[f"{value_col}_percent_change_with_vs_no_cache"] = (
                100 * paired[f"{value_col}_delta_with_minus_no_cache"] / paired[no_cache_col].replace(0, np.nan)
            )
        return paired.sort_values(id_cols)

    def _summarize_cache_effect_pairs(self, cache_pairs: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
        """Summarize paired with-cache vs no-cache effects across configured environments."""
        if cache_pairs.empty:
            return pd.DataFrame()
        grouping_cols = ["benchmark_family", "cache_stack", "cache_pair_name", "modality", "is_preloaded"]
        return self._summarize_cache_effect_pairs_for_groups(cache_pairs, metrics, grouping_cols)

    def _summarize_cache_effect_pairs_by_method(self, cache_pairs: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
        """Summarize paired with-cache vs no-cache effects across modalities for each method/access stack."""
        if cache_pairs.empty:
            return pd.DataFrame()
        grouping_cols = ["benchmark_family", "cache_stack", "cache_pair_name", "is_preloaded"]
        return self._summarize_cache_effect_pairs_for_groups(cache_pairs, metrics, grouping_cols)

    def _summarize_cache_effect_pairs_for_groups(
        self, cache_pairs: pd.DataFrame, metrics: List[str], grouping_cols: List[str]
    ) -> pd.DataFrame:
        """Summarize paired with-cache vs no-cache effects for a requested grouping."""
        rows = []
        for group_values, group_df in cache_pairs.groupby(grouping_cols, dropna=False):
            if not isinstance(group_values, tuple):
                group_values = (group_values,)
            row = dict(zip(grouping_cols, group_values))
            row["paired_conditions_n"] = len(group_df)
            row["environment_dates"] = ", ".join(map(str, sorted(group_df["environment_date"].dropna().unique())))
            if "modality" not in grouping_cols:
                row["modalities"] = ", ".join(map(str, sorted(group_df["modality"].dropna().unique())))
            for value_col in ["ordinary_runtime_median", *metrics]:
                no_cache_col = f"{value_col}_no_cache"
                with_cache_col = f"{value_col}_with_cache"
                ratio_col = f"{value_col}_ratio_with_over_no_cache"
                pct_col = f"{value_col}_percent_change_with_vs_no_cache"
                if no_cache_col not in group_df.columns or with_cache_col not in group_df.columns:
                    continue
                row[f"{value_col}_no_cache_median"] = self._safe_median(group_df[no_cache_col])
                row[f"{value_col}_with_cache_median"] = self._safe_median(group_df[with_cache_col])
                row[f"{value_col}_ratio_with_over_no_cache_median"] = self._safe_median(group_df[ratio_col])
                row[f"{value_col}_percent_change_with_vs_no_cache_median"] = self._safe_median(group_df[pct_col])
            rows.append(row)
        return pd.DataFrame(rows).sort_values(grouping_cols)

    def _write_cache_effect_summaries(self, matched_df: pd.DataFrame, metrics: List[str]) -> None:
        """Write environment-aware cache-effect summary tables for environments_all."""
        if self.summary_tables_directory is None or self.environment_label != "all":
            return
        cache_pairs = self._build_cache_effect_pair_table(matched_df, metrics)
        if cache_pairs.empty:
            self._record_skipped_output(
                "table", "cache_effect_paired_conditions.csv", "No cache/no-cache pairs available."
            )
            return
        cache_summary = self._summarize_cache_effect_pairs(cache_pairs, metrics)
        cache_method_summary = self._summarize_cache_effect_pairs_by_method(cache_pairs, metrics)
        cache_pairs.to_csv(self.summary_tables_directory / "cache_effect_paired_conditions.csv", index=False)
        cache_summary.to_csv(self.summary_tables_directory / "cache_effect_summary.csv", index=False)
        cache_method_summary.to_csv(self.summary_tables_directory / "cache_effect_method_summary.csv", index=False)

    def _build_preload_effect_pair_table(self, matched_df: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
        """Build matched preloaded vs non-preloaded summaries from matched conditions."""
        preload_df = matched_df.copy()
        if preload_df.empty:
            return pd.DataFrame()
        preload_df = preload_df[preload_df["is_preloaded"].isin([True, False])]
        if preload_df.empty:
            return pd.DataFrame()

        preload_df["cache_stack"] = preload_df["benchmark_name_clean"].map(self._cache_stack_from_benchmark_name)
        preload_df["cache_state"] = preload_df["benchmark_name_clean"].map(self._cache_state_from_benchmark_name)
        preload_df["cache_state"] = preload_df["cache_state"].fillna("not_applicable")
        preload_df["cache_stack"] = preload_df["cache_stack"].fillna("not_applicable")
        preload_df["preload_pair_name"] = (
            preload_df["benchmark_name_clean"]
            .astype(str)
            .str.replace(" preloaded", "", regex=False)
            .str.replace("  ", " ", regex=False)
            .str.strip()
        )
        preload_df["preload_state"] = preload_df["is_preloaded"].map({False: "not_preloaded", True: "preloaded"})
        preload_df["slice_number"] = preload_df["slice_number"].fillna("not_applicable")
        preload_df["scaling_value"] = preload_df["scaling_value"].fillna("not_applicable")

        value_cols = ["ordinary_runtime_median", *metrics]
        id_cols = [
            "environment_id",
            "environment_date",
            "benchmark_family",
            "modality",
            "preload_pair_name",
            "cache_stack",
            "cache_state",
            "slice_number",
            "scaling_value",
        ]
        paired = preload_df.pivot_table(
            index=id_cols,
            columns="preload_state",
            values=value_cols,
            aggfunc="first",
            dropna=True,
        )
        paired.columns = [f"{value_col}_{preload_state}" for value_col, preload_state in paired.columns]
        paired = paired.reset_index()
        paired = paired.rename(columns={"preload_pair_name": "benchmark_name_clean"})
        id_cols = ["benchmark_name_clean" if col == "preload_pair_name" else col for col in id_cols]
        paired["slice_number"] = paired["slice_number"].where(paired["slice_number"] != "not_applicable", np.nan)
        paired["scaling_value"] = paired["scaling_value"].where(paired["scaling_value"] != "not_applicable", np.nan)

        required_cols = ["ordinary_runtime_median_not_preloaded", "ordinary_runtime_median_preloaded"]
        paired = paired.dropna(subset=required_cols, how="any")
        for value_col in value_cols:
            not_preloaded_col = f"{value_col}_not_preloaded"
            preloaded_col = f"{value_col}_preloaded"
            if not_preloaded_col not in paired.columns or preloaded_col not in paired.columns:
                continue
            paired[f"{value_col}_delta_preloaded_minus_not_preloaded"] = (
                paired[preloaded_col] - paired[not_preloaded_col]
            )
            paired[f"{value_col}_ratio_preloaded_over_not_preloaded"] = paired[preloaded_col] / paired[
                not_preloaded_col
            ].replace(0, np.nan)
            paired[f"{value_col}_percent_change_preloaded_vs_not_preloaded"] = (
                100
                * paired[f"{value_col}_delta_preloaded_minus_not_preloaded"]
                / paired[not_preloaded_col].replace(0, np.nan)
            )
        return paired.sort_values(id_cols)

    def _summarize_preload_effect_pairs(self, preload_pairs: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
        """Summarize matched preloaded vs non-preloaded effects by method and modality."""
        if preload_pairs.empty:
            return pd.DataFrame()
        grouping_cols = ["benchmark_family", "benchmark_name_clean", "cache_stack", "cache_state", "modality"]
        rows = []
        for group_values, group_df in preload_pairs.groupby(grouping_cols, dropna=False):
            row = dict(zip(grouping_cols, group_values))
            row["paired_conditions_n"] = len(group_df)
            row["environment_dates"] = ", ".join(map(str, sorted(group_df["environment_date"].dropna().unique())))
            for value_col in ["ordinary_runtime_median", *metrics]:
                not_preloaded_col = f"{value_col}_not_preloaded"
                preloaded_col = f"{value_col}_preloaded"
                ratio_col = f"{value_col}_ratio_preloaded_over_not_preloaded"
                pct_col = f"{value_col}_percent_change_preloaded_vs_not_preloaded"
                if not_preloaded_col not in group_df.columns or preloaded_col not in group_df.columns:
                    continue
                row[f"{value_col}_not_preloaded_median"] = self._safe_median(group_df[not_preloaded_col])
                row[f"{value_col}_preloaded_median"] = self._safe_median(group_df[preloaded_col])
                row[f"{value_col}_ratio_preloaded_over_not_preloaded_median"] = self._safe_median(group_df[ratio_col])
                row[f"{value_col}_percent_change_preloaded_vs_not_preloaded_median"] = self._safe_median(
                    group_df[pct_col]
                )
            rows.append(row)
        return pd.DataFrame(rows).sort_values(grouping_cols)

    def _write_preload_effect_summaries(self, matched_df: pd.DataFrame, metrics: List[str]) -> None:
        """Write environment-aware preload-effect summary tables for environments_all."""
        if self.summary_tables_directory is None or self.environment_label != "all":
            return
        preload_pairs = self._build_preload_effect_pair_table(matched_df, metrics)
        if preload_pairs.empty:
            self._record_skipped_output("table", "preload_effect_paired_conditions.csv", "No preload pairs available.")
            return
        preload_summary = self._summarize_preload_effect_pairs(preload_pairs, metrics)
        preload_pairs.to_csv(self.summary_tables_directory / "preload_effect_paired_conditions.csv", index=False)
        preload_summary.to_csv(self.summary_tables_directory / "preload_effect_summary.csv", index=False)

    def plot_network_runtime_correlations(self, db: BenchmarkDatabase) -> None:
        """Generate pooled network/runtime matched tables and correlation plots for configured environments."""
        print("Plotting pooled network-runtime correlation analysis...")
        matched_df = self._build_network_runtime_matched_table(db)
        if matched_df.empty:
            self._record_skipped_output(
                "network analytics",
                "network_runtime_matched_conditions.csv",
                "No matched ordinary/network rows available.",
            )
            return

        available_metrics = [metric for metric in NETWORK_METRIC_LABELS if metric in matched_df.columns]
        available_metrics = [metric for metric in available_metrics if matched_df[metric].notna().any()]
        if not available_metrics:
            self._record_skipped_output(
                "network analytics", "network_runtime_correlations_pooled.csv", "No non-null network metrics available."
            )
            return

        if self.summary_tables_directory is not None:
            matched_df.to_csv(self.summary_tables_directory / "network_runtime_matched_conditions.csv", index=False)
            self._write_cache_effect_summaries(matched_df, available_metrics)
            self._write_preload_effect_summaries(matched_df, available_metrics)

        pooled = self._compute_network_runtime_pooled_correlations_by_modality(matched_df, available_metrics)
        pooled["environment_scope"] = "pooled across configured official-machine software environments"
        by_environment = self._compute_network_runtime_correlations(
            matched_df, available_metrics, ["environment_date", "benchmark_family"]
        )
        if self.summary_tables_directory is not None:
            pooled.to_csv(self.summary_tables_directory / "network_runtime_correlations_pooled.csv", index=False)
            by_environment.to_csv(
                self.summary_tables_directory / "network_runtime_correlations_by_environment.csv", index=False
            )
            sensitivity = (
                by_environment.groupby(["benchmark_family", "network_metric", "network_metric_label"], dropna=False)
                .agg(
                    environments_with_defined_spearman=("spearman_r", "count"),
                    min_spearman_r=("spearman_r", "min"),
                    max_spearman_r=("spearman_r", "max"),
                )
                .reset_index()
            )
            sensitivity["spearman_sign_changes_across_environments"] = (sensitivity["min_spearman_r"] < 0) & (
                sensitivity["max_spearman_r"] > 0
            )
            sensitivity.to_csv(
                self.summary_tables_directory / "network_runtime_correlation_sensitivity_summary.csv", index=False
            )

        self._plot_network_runtime_scatter_matrix(
            matched_df,
            available_metrics,
            "network_runtime_scatter_matrix_loglog.pdf",
            log_scale=True,
        )
        self._plot_network_runtime_scatter_matrix(
            matched_df,
            available_metrics,
            "network_runtime_scatter_matrix_linear.pdf",
            log_scale=False,
        )
        self._plot_network_runtime_heatmap(pooled, "network_runtime_correlation_heatmap.pdf")

    def _plot_network_runtime_scatter_matrix(
        self, matched_df: pd.DataFrame, metrics: List[str], filename: str, log_scale: bool = False
    ) -> None:
        """Plot matched ordinary runtime against all available network metrics in one matrix."""
        metrics = [metric for metric in metrics if metric in matched_df.columns and matched_df[metric].notna().any()]
        if not metrics:
            self._record_skipped_output("plot", filename, "No network metrics available for scatter matrix.")
            return

        benchmark_families = ["remote_file_opening_backend", "remote_file_reading_pynwb", "remote_slicing"]
        family_titles = {
            "remote_file_opening_backend": "Remote backend file opening",
            "remote_file_reading_pynwb": "Remote PyNWB file reading",
            "remote_slicing": "Remote slicing",
        }
        modality_order = ["Ecephys", "Ophys", "Icephys"]
        palette = dict(zip(modality_order, sns.color_palette("colorblind", n_colors=len(modality_order))))
        fig, axes = plt.subplots(
            len(metrics),
            len(benchmark_families),
            figsize=(13.5, 4.5 * len(metrics)),
            squeeze=False,
        )
        for row_index, metric in enumerate(metrics):
            for col_index, benchmark_family in enumerate(benchmark_families):
                ax = axes[row_index, col_index]
                plot_df = matched_df[
                    matched_df["benchmark_family"].eq(benchmark_family)
                    & matched_df[metric].notna()
                    & matched_df["ordinary_runtime_median"].notna()
                ]
                if log_scale:
                    plot_df = plot_df[(plot_df[metric] > 0) & (plot_df["ordinary_runtime_median"] > 0)]
                if plot_df.empty:
                    ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
                    ax.set_axis_off()
                    continue
                corr_df = plot_df[["ordinary_runtime_median", metric]].dropna()
                spearman_r = self._safe_correlation(corr_df, "ordinary_runtime_median", metric, "spearman")
                pearson_r = self._safe_correlation(corr_df, "ordinary_runtime_median", metric, "pearson")
                sns.scatterplot(
                    data=plot_df,
                    x=metric,
                    y="ordinary_runtime_median",
                    hue="modality",
                    hue_order=modality_order,
                    palette=palette,
                    s=18,
                    alpha=0.65,
                    linewidth=0,
                    ax=ax,
                    legend=row_index == 0 and col_index == len(benchmark_families) - 1,
                )
                fit_x = plot_df[metric].to_numpy(dtype=float)
                fit_y = plot_df["ordinary_runtime_median"].to_numpy(dtype=float)
                if len(plot_df) >= 3 and np.unique(fit_x).size > 1 and np.unique(fit_y).size > 1:
                    if log_scale:
                        fit_x_values = np.log10(fit_x)
                        fit_y_values = np.log10(fit_y)
                        x_line = np.geomspace(fit_x.min(), fit_x.max(), 100)
                        slope, intercept = np.polyfit(fit_x_values, fit_y_values, 1)
                        y_line = 10 ** (slope * np.log10(x_line) + intercept)
                    else:
                        x_line = np.linspace(fit_x.min(), fit_x.max(), 100)
                        slope, intercept = np.polyfit(fit_x, fit_y, 1)
                        y_line = slope * x_line + intercept
                    ax.plot(x_line, y_line, color="black", linewidth=1.0, alpha=0.8)
                if log_scale:
                    ax.set_xscale("log")
                    ax.set_yscale("log")
                annotation = f"n={len(corr_df)}\nρ={spearman_r:.2f}\nr={pearson_r:.2f}"
                ax.text(
                    0.03,
                    0.97,
                    annotation,
                    ha="left",
                    va="top",
                    transform=ax.transAxes,
                    fontsize=8,
                    bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.75},
                )
                ax.set_xlabel(NETWORK_METRIC_LABELS.get(metric, metric) if row_index == len(metrics) - 1 else "")
                ax.set_ylabel("Runtime (s)" if col_index == 0 else "")
                ax.set_box_aspect(1)
                if row_index == 0:
                    ax.set_title(family_titles.get(benchmark_family, benchmark_family))
                if col_index == 0:
                    ax.text(
                        -0.32,
                        0.5,
                        NETWORK_METRIC_LABELS.get(metric, metric),
                        ha="right",
                        va="center",
                        rotation=90,
                        transform=ax.transAxes,
                        fontsize=9,
                    )
                if ax.get_legend() is not None:
                    ax.legend(title="Modality", loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)
        fig.suptitle(
            "Matched ordinary runtime vs. network metrics, pooled across configured official-machine environments"
            f" ({'log-log' if log_scale else 'linear-linear'} axes)",
            y=0.995,
        )
        caption = "Each point is a matched environment-aware condition. Black lines show least-squares fits on the plotted scale."
        fig.text(0.5, 0.003, caption, ha="center", va="bottom", fontsize=9, style="italic")
        plt.tight_layout(rect=(0.08, 0.02, 0.92, 0.985))
        plt.savefig(self.output_directory / filename, dpi=300, bbox_inches="tight")
        plt.close()

    def _plot_network_runtime_heatmap(self, correlations: pd.DataFrame, filename: str) -> None:
        """Plot pooled Spearman correlations as family-specific modality heatmaps."""
        if correlations.empty or "spearman_r" not in correlations.columns:
            self._record_skipped_output("plot", filename, "No pooled correlations available for heatmap.")
            return
        if "modality_group" not in correlations.columns:
            correlations = correlations.copy()
            correlations["modality_group"] = "all"

        benchmark_families = ["remote_file_opening_backend", "remote_file_reading_pynwb", "remote_slicing"]
        modality_order = ["all", "Ecephys", "Ophys", "Icephys"]
        metric_labels = [NETWORK_METRIC_LABELS[metric] for metric in NETWORK_METRIC_LABELS]
        metric_labels = [label for label in metric_labels if label in correlations["network_metric_label"].unique()]
        heatmaps = []
        for benchmark_family in benchmark_families:
            family_correlations = correlations[correlations["benchmark_family"] == benchmark_family]
            heatmap_df = family_correlations.pivot_table(
                index="modality_group",
                columns="network_metric_label",
                values="spearman_r",
                aggfunc="first",
                observed=False,
            )
            heatmap_df = heatmap_df.reindex(index=modality_order, columns=metric_labels)
            heatmaps.append((benchmark_family, heatmap_df))

        if not heatmaps or all(heatmap_df.dropna(how="all").empty for _, heatmap_df in heatmaps):
            self._record_skipped_output("plot", filename, "Pooled correlations are undefined or null-only.")
            return

        fig = plt.figure(figsize=(13, 10))
        gs = fig.add_gridspec(3, 2, width_ratios=[40, 1], hspace=0.35, wspace=0.04)
        axes = [fig.add_subplot(gs[0, 0])]
        axes.append(fig.add_subplot(gs[1, 0], sharex=axes[0]))
        axes.append(fig.add_subplot(gs[2, 0], sharex=axes[0]))
        cbar_ax = fig.add_subplot(gs[:, 1])
        family_titles = {
            "remote_file_opening_backend": "Remote backend file opening",
            "remote_file_reading_pynwb": "Remote PyNWB file reading",
            "remote_slicing": "Remote slicing",
        }
        for index, (ax, (benchmark_family, heatmap_df)) in enumerate(zip(axes, heatmaps)):
            sns.heatmap(
                heatmap_df,
                annot=True,
                fmt=".2f",
                cmap="vlag",
                center=0,
                vmin=-1,
                vmax=1,
                ax=ax,
                cbar=index == 0,
                cbar_ax=cbar_ax if index == 0 else None,
                cbar_kws={"label": "Spearman r"} if index == 0 else None,
            )
            ax.set(xlabel="", ylabel="Modality subset")
            ax.set_title(family_titles.get(benchmark_family, benchmark_family))
            ax.tick_params(axis="y", rotation=0)
            if index < len(axes) - 1:
                ax.tick_params(axis="x", labelbottom=False, bottom=False)
        axes[-1].set_xlabel("Network metric")
        fig.suptitle("Pooled correlations between ordinary runtime and network metrics", y=0.98)
        caption = "Correlations are pooled across configured official-machine software environments after environment-aware matching."
        fig.text(0.5, -0.01, caption, ha="center", va="top", fontsize=9, wrap=True, style="italic")
        for tick in axes[-1].get_xticklabels():
            tick.set_rotation(35)
            tick.set_ha("right")
        fig.subplots_adjust(left=0.12, right=0.94, bottom=0.23, top=0.90)
        plt.savefig(self.output_directory / filename, dpi=300, bbox_inches="tight")
        plt.close()

    @staticmethod
    def _add_annotations_df(intersections_df: pl.DataFrame, order: List[str], **kwargs):
        """Add intersection annotations to plot."""
        ax = plt.gca()

        # Get the grouping values from data
        all_modalities = kwargs["data"]["modality"].unique()
        assert len(all_modalities) == 1, "Expected a single modality per subplot."

        is_preloaded = kwargs["data"]["is_preloaded"].unique()
        assert len(is_preloaded) == 1, "Expected a single preloaded parameter per subplot."

        summary_text = ["# slices to intersect with download time \n"]
        modality_intersections = intersections_df.query(
            f'modality == "{all_modalities[0]}" and is_preloaded == {is_preloaded[0]}'
        )
        for label in order:
            row = modality_intersections.query(f'benchmark_name_clean == "{label}"')
            if not row.empty:
                summary_text.append(f"{label}: {row['intersection_slice'].tolist()[0]:.2f}\n")

        ax.text(
            0.1,
            0.9,
            "".join(summary_text),
            transform=ax.transAxes,
            fontsize=8,
            ha="left",
            va="top",
        )

    def _compute_heatmap_order(self, heatmap_df: pd.DataFrame) -> List[str]:
        """
        Compute ordering for heatmap based on:
        1. Format type (lindi → zarr → hdf5)
        2. Average performance (ascending) within each format type

        Args:
            heatmap_df: Pivoted DataFrame with benchmark names as index and modalities as columns

        Returns:
            List of benchmark names in sorted order
        """
        # Calculate mean value across all modalities (columns)
        avg_performance = heatmap_df.mean(axis=1).to_frame(name="avg_value")

        # Categorize by format type
        def get_format_order(name):
            if "lindi" in name.lower():
                return 0  # lindi first
            elif "zarr" in name.lower():
                return 1  # zarr second
            elif "hdf5" in name.lower():
                return 2  # hdf5 third
            else:
                return 3  # other last

        avg_performance["format_order"] = avg_performance.index.map(get_format_order)

        # Sort by format type, then by average value (ascending = fastest first)
        sorted_df = avg_performance.sort_values(["format_order", "avg_value"])

        return sorted_df.index.tolist()

    def _create_heatmap_df(
        self, df: pl.DataFrame, group: str, metric_order: Optional[List[str]] = None, aggfunc: str = "mean"
    ) -> pd.DataFrame:
        """Prepare data for heatmap visualization."""
        heatmap_df = (
            df.to_pandas()
            .pivot_table(index=group, columns="modality", values="value", aggfunc=aggfunc)
            .reindex(["Ecephys", "Ophys", "Icephys"], axis=1)
        )

        # Compute order from the pivoted data if not provided
        if metric_order is None:
            metric_order = self._compute_heatmap_order(heatmap_df)

        return heatmap_df.reindex(metric_order)

    def plot_benchmark_heatmap(
        self,
        df: pl.LazyFrame,
        metric_order: Optional[List[str]] = None,
        group: str = "benchmark_name_clean",
        ax: Optional[plt.Axes] = None,
        title: str = "",
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
        aggfunc: str = "mean",
    ) -> plt.Axes:
        """Create heatmap visualization of benchmark results."""
        collected_df = df.collect()

        if collected_df.to_pandas().empty:
            self._record_skipped_output(
                "plot", title or "benchmark heatmap", "No data available for benchmark heatmap."
            )
            return

        # Create heatmap dataframe (which will compute order if not provided)
        heatmap_df = self._create_heatmap_df(collected_df, group, metric_order, aggfunc=aggfunc)

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 8))

        sns.heatmap(data=heatmap_df, annot=True, fmt=".3g", cmap="OrRd", ax=ax, vmin=vmin, vmax=vmax)
        ax.set(xlabel="", ylabel="")
        if group == "benchmark_name_clean":
            ax.set_yticks(np.arange(len(heatmap_df.index)) + 0.5)
            ax.set_yticklabels(self._display_method_labels(heatmap_df.index.tolist()))

        # Add star for best method in each modality
        for j, col in enumerate(heatmap_df.columns):
            min_idx = heatmap_df[col].idxmin()
            i = heatmap_df.index.get_loc(min_idx)
            ax.text(j + 0.5, i + 0.5, "        *", fontsize=20, ha="center", va="center", color="black", weight="bold")

        ax.set_title(title)

        return ax

    def plot_benchmark_dist(
        self,
        df: pd.DataFrame,
        group: str,
        metric_order: List[str],
        filename: str,
        row: Optional[str] = None,
        sharex: bool = True,
        add_annotations: bool = True,
        kind: str = "box",
        palette: str = "Paired",
        catplot_kwargs: Optional[Dict[str, Any]] = None,
        caption: str = None,
        xlabel: str = "Time (s)",
        row_xlabels: Optional[Dict[str, str]] = None,
    ):
        """Create distribution plot for benchmarks."""
        catplot_kwargs = catplot_kwargs or {}
        if metric_order is not None:
            # Keep only the explicitly requested benchmark methods. Seaborn's ``order`` controls
            # the displayed category order, but filtering here prevents unintended methods from
            # leaking into annotations, legends, or future plot/statistics code paths.
            df = df[df[group].isin(metric_order)]

        if df.empty:
            self._record_skipped_output("plot", filename, "No data available to plot.")
            return

        g = sns.catplot(
            data=df,
            x="value",
            y=group,
            col="modality",
            row=row,
            hue=group,
            sharex=sharex,
            palette=palette,
            kind=kind,
            order=metric_order,
            legend=False,
            **catplot_kwargs,
        )

        if add_annotations:
            g.map_dataframe(self._add_mean_std_annotations, value="value", group=group, order=metric_order)

        g.set(xlabel=xlabel, ylabel=df["benchmark_name_label"].iloc[0])
        if row is not None and row_xlabels is not None:
            for row_index, row_name in enumerate(g.row_names):
                row_xlabel = row_xlabels.get(row_name, xlabel)
                for ax in g.axes[row_index, :]:
                    ax.set_xlabel(row_xlabel)

        for ax in g.axes.flat:
            wrapped_title = "\n".join(textwrap.wrap(ax.get_title(), width=50))
            ax.set_title(wrapped_title)
            if group == "benchmark_name_clean" and metric_order is not None:
                ax.set_yticks(range(len(metric_order)))
                ax.set_yticklabels(self._display_method_labels(metric_order))

        # Add figure caption
        if kind == "strip" and caption is not None:
            caption += "Each point represents a single benchmark run. "
        caption = self._add_environment_caption(caption)
        g.figure.text(0.5, -0.01, caption, ha="center", va="top", fontsize=9, wrap=True, style="italic")

        sns.despine()
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches="tight")
        plt.close()

    def plot_benchmark_slices_vs_time(
        self,
        df: pd.DataFrame,
        group: str,
        y_value: str,
        metric_order: List[str],
        filename: Path,
        row: Optional[str] = None,
        sharex: bool = True,
        intersections_df: Optional[pl.DataFrame] = None,
        caption=None,
    ):
        """Plot benchmark performance vs slice size."""
        if metric_order is not None:
            # Keep only the explicitly requested benchmark methods. Seaborn's ``hue_order``
            # controls display order, but filtering here makes the plotted dataset auditable and
            # prevents unintended methods from affecting future plot/statistics code paths.
            df = df[df[group].isin(metric_order)]

        if df.empty:
            self._record_skipped_output("plot", filename, "No data available to plot.")
            return

        g = sns.catplot(
            data=df,
            x="slice_number",
            y=y_value,
            col="modality",
            row=row,
            hue=group,
            hue_order=metric_order,
            sharex=sharex,
            palette="Paired",
            sharey=False,
            kind="point",
        )

        if caption is not None:
            caption = self._add_environment_caption(caption)
            g.figure.text(0.5, -0.01, caption, ha="center", va="top", fontsize=9, wrap=True, style="italic")

        # Add intersection annotations
        if intersections_df is not None:
            g.map_dataframe(self._add_annotations_df, intersections_df=intersections_df, order=metric_order)

        g.set(xlabel="Relative slice size", ylabel="Time (s)")
        if metric_order is not None:
            sns.move_legend(g, "upper right", labels=self._display_method_labels(metric_order))
        sns.despine()
        plt.savefig(filename, dpi=300, bbox_inches="tight")
        plt.close()

    def plot_read_benchmarks(
        self,
        db: BenchmarkDatabase,
        order: List[str] = None,
        benchmark_type: str = "time_remote_file_reading",
        col_name: str = "benchmark_name_clean",
        network_tracking: bool = False,
        kind: str = "box",
        suffix: str = "_pynwb",
    ):
        """Plot read benchmark results."""
        output_family = "PyNWB" if suffix == "_pynwb" else "backend"
        print(f"Plotting {output_family} read benchmarks for {benchmark_type}...")

        filtered_df = db.filter_tests(benchmark_type).collect()
        prefix = self._get_filename_prefix(network_tracking)

        # Create base plot kwargs
        caption_suffix = " using pynwb. " if suffix == "_pynwb" else ". "
        caption = (
            f"Benchmark execution times across different methods and modalities{caption_suffix}"
            "Text annotations, if present, display mean ± standard deviation and sample size (n). "
        )
        figure_filename = self.output_directory / self._filename_with_environment_postfix(f"{prefix}file_open", suffix)
        base_kwargs = self._create_plot_kwargs(
            df=filtered_df.to_pandas(),
            group=col_name,
            order=self.pynwb_read_order if order is None else order,
            filename=figure_filename,
            kind=kind,
            caption=caption,
        )

        # Add network tracking specific options
        if network_tracking:
            base_kwargs.update({"row": "variable", "sharex": "row", "row_xlabels": NETWORK_METRIC_LABELS})
            summary_group_cols = ["benchmark_name_type", "variable", col_name, "modality"]
        else:
            summary_group_cols = ["benchmark_name_type", col_name, "modality"]

        summary_df = base_kwargs["df"]
        if base_kwargs["metric_order"] is not None:
            summary_df = summary_df[summary_df[col_name].isin(base_kwargs["metric_order"])]
        self._write_summary_table(
            df=summary_df,
            group_cols=summary_group_cols,
            value_col="value",
            filename=f"{figure_filename.stem}_summary.csv",
        )

        # Plot box plot
        self.plot_benchmark_dist(**base_kwargs)

        # Plot scatter plot
        base_kwargs.update(
            {
                "catplot_kwargs": dict(),
                "kind": "strip",
                "add_annotations": False,
                "filename": self.output_directory
                / self._filename_with_environment_postfix(f"{prefix}file_open_scatter", suffix),
            }
        )
        self.plot_benchmark_dist(**base_kwargs)

    def plot_slice_benchmarks(
        self,
        db: BenchmarkDatabase,
        order: List[str] = None,
        benchmark_type: str = "time_remote_slicing",
        col_name: str = "benchmark_name_clean",
        network_tracking: bool = False,
        kind: str = "box",
    ):
        """Plot slice benchmark results."""
        print(f"Plotting slice benchmarks for {benchmark_type}...")

        filtered_df = db.filter_tests(benchmark_type).collect()
        prefix = self._get_filename_prefix(network_tracking)

        # Create base plot kwargs
        base_kwargs = self._create_plot_kwargs(
            df=filtered_df,
            group=col_name,
            order=self.pynwb_read_order if order is None else order,
            filename=None,
            kind=kind,
            row="is_preloaded",
        )

        if network_tracking:
            summary_group_cols = [
                "benchmark_name_type",
                "slice_number",
                "is_preloaded",
                "variable",
                col_name,
                "modality",
            ]
            for preload_value, preload_label, preload_caption in [
                (False, "not_preloaded", "not preloaded"),
                (True, "preloaded", "preloaded"),
            ]:
                preload_df = filtered_df.filter(pl.col("is_preloaded") == preload_value)
                network_kwargs = base_kwargs.copy()
                network_kwargs.update(
                    {
                        "df": preload_df,
                        "row": "variable",
                        "sharex": "row",
                        "row_xlabels": NETWORK_METRIC_LABELS,
                    }
                )
                self._write_summary_table(
                    df=preload_df.to_pandas(),
                    group_cols=summary_group_cols,
                    value_col="value",
                    filename=f"{prefix}slicing_{preload_label}{self.environment_filename_postfix}_summary.csv",
                )

                for slice_num, slice_df in enumerate(preload_df.partition_by("slice_number")):
                    figure_filename = self.output_directory / self._filename_with_environment_postfix(
                        f"{prefix}slicing_{preload_label}_range{slice_num}"
                    )
                    self._write_summary_table(
                        df=slice_df.to_pandas(),
                        group_cols=summary_group_cols,
                        value_col="value",
                        filename=f"{Path(figure_filename).stem}_summary.csv",
                    )
                    network_kwargs.update(
                        {
                            "df": slice_df.to_pandas(),
                            "filename": figure_filename,
                            "caption": (
                                f"Network-tracking benchmark measurements across different methods and modalities for slice data "
                                f"(range = {slice_num}, {preload_caption}). "
                                "Rows separate network metrics. Text annotations, if present, display mean ± standard deviation and sample size (n). "
                            ),
                        }
                    )
                    self.plot_benchmark_dist(**network_kwargs)

                network_kwargs.update(
                    {
                        "df": preload_df.to_pandas(),
                        "catplot_kwargs": dict(),
                        "kind": "strip",
                        "add_annotations": False,
                        "filename": self.output_directory
                        / self._filename_with_environment_postfix(f"{prefix}slicing_{preload_label}_scatter"),
                        "caption": (
                            f"Network-tracking benchmark measurements across different methods and modalities for slice data "
                            f"({preload_caption}). Each point represents a single benchmark run. Rows separate network metrics. "
                        ),
                    }
                )
                self.plot_benchmark_dist(**network_kwargs)
            return
        else:
            summary_group_cols = ["benchmark_name_type", "slice_number", "is_preloaded", col_name, "modality"]

        summary_df = base_kwargs["df"].to_pandas() if isinstance(base_kwargs["df"], pl.DataFrame) else base_kwargs["df"]
        self._write_summary_table(
            df=summary_df,
            group_cols=summary_group_cols,
            value_col="value",
            filename=f"{prefix}slicing{self.environment_filename_postfix}_summary.csv",
        )

        # Plot box plot for each slice value
        for slice_num, slice_df in enumerate(base_kwargs["df"].partition_by("slice_number")):
            figure_filename = self.output_directory / self._filename_with_environment_postfix(
                f"{prefix}slicing_range{slice_num}"
            )
            self._write_summary_table(
                df=slice_df.to_pandas(),
                group_cols=summary_group_cols,
                value_col="value",
                filename=f"{Path(figure_filename).stem}_summary.csv",
            )
            base_kwargs.update(
                {
                    "df": slice_df.to_pandas(),
                    "filename": figure_filename,
                    "caption": (
                        f"Benchmark execution times across different methods and modalities for slice data (range = {slice_num})."
                        "Text annotations, if present, display mean ± standard deviation and sample size (n). "
                    ),
                }
            )
            self.plot_benchmark_dist(**base_kwargs)

        # Plot scatter plot
        base_kwargs.update(
            {
                "df": filtered_df.to_pandas(),
                "catplot_kwargs": dict(),
                "kind": "strip",
                "add_annotations": False,
                "filename": self.output_directory / self._filename_with_environment_postfix(f"{prefix}slicing_scatter"),
                "caption": (
                    "Benchmark execution times across different methods and modalities for slice data across all slice ranges. "
                ),
            }
        )
        self.plot_benchmark_dist(**base_kwargs)

    def plot_linear_extrapolation_with_intersection(
        self,
        remote_group,
        local_group,
        benchmark_name: str,
        ax: plt.Axes,
        color: str,
        title: str = "",
        xlabel: str = "Number of slices",
        ylabel: str = "Time (s)",
    ):
        """Plot linear extrapolation showing intersection between remote and local approaches."""
        if len(remote_group["slice_number"].unique()) <= 1 or len(local_group["slice_number"].unique()) <= 1:
            return None  # Not enough data points to fit line

        # Calculate linear fits
        m1, b1 = np.polyfit(remote_group["slice_number"], remote_group["total_time"], 1)
        m2, b2 = np.polyfit(local_group["slice_number"], local_group["total_time"], 1)

        if abs(m1 - m2) < 1e-10:  # parallel lines
            return None

        intersection_x = (b2 - b1) / (m1 - m2)
        intersection_y = m1 * intersection_x + b1

        if intersection_x < 0 or intersection_y < 0:
            # TODO add note to figure that intersection was not plotted
            return None  # Intersection is not in the positive quadrant

        # Create x-range from 0 to slightly past intersection
        x_max = max(intersection_x * 1.2, intersection_x + 2)
        x_range = np.linspace(0, x_max, 100)

        # Calculate y-values for both lines
        y_remote = m1 * x_range + b1
        y_local = m2 * x_range + b2

        # Plot the fitted lines and mark intersection point
        ax.plot(
            x_range,
            y_remote,
            color=color,
            linestyle="solid",
            linewidth=2,
            label=self._display_method_label(benchmark_name),
        )
        if benchmark_name.startswith("hdf5"):
            download_color = sns.color_palette("Greens")[-1]
        elif benchmark_name.startswith("zarr"):
            download_color = sns.color_palette("Reds")[-1]
        else:
            download_color = sns.color_palette("Blues")[-1]
        ax.plot(x_range, y_local, color=download_color, linestyle="dashed", linewidth=2)
        ax.plot(intersection_x, intersection_y, "x", color=color, markersize=8, zorder=5)
        ax.set(title=title, xlabel=xlabel, ylabel=ylabel)

        return ax

    def plot_download_vs_stream_benchmarks(
        self,
        db: BenchmarkDatabase,
        order: List[str] = None,
        network_tracking: bool = False,
    ):
        """Plot download vs stream benchmark comparison."""
        print("Plotting download vs stream benchmark comparison...")
        prefix = self._get_filename_prefix(network_tracking)
        base_filename = self.output_directory / f"{prefix}slicing"
        remote_read_figure_filename = Path(f"{base_filename}_with_remote_read{self.environment_filename_postfix}.pdf")
        remote_range_figure_filename = Path(f"{base_filename}_range{self.environment_filename_postfix}.pdf")
        local_read_figure_filename = Path(f"{base_filename}_with_local_read{self.environment_filename_postfix}.pdf")
        extrapolation_figure_filename = Path(
            f"{base_filename}_with_extrapolation{self.environment_filename_postfix}.pdf"
        )
        plot_kwargs = {
            "group": "benchmark_name_clean",
            "row": "variable" if network_tracking else "is_preloaded",
            "sharex": "row" if network_tracking else True,
        }

        # get remote read + slice times combined with baseline number of slices (indicates file read only time)
        remote_slice_and_read_df = db.combine_read_and_slice_times(
            read_col_name="time_remote_file_reading", slice_col_name="time_remote_slicing", with_baseline=True
        )
        remote_slice_and_read_pdf = remote_slice_and_read_df.collect().to_pandas()
        self._write_summary_table(
            df=remote_slice_and_read_pdf,
            group_cols=["slice_number", "is_preloaded", "benchmark_name_clean", "modality"],
            value_col="total_time",
            filename=f"{remote_read_figure_filename.stem}_summary.csv",
        )
        self._write_summary_table(
            df=remote_slice_and_read_pdf,
            group_cols=["slice_number", "is_preloaded", "benchmark_name_clean", "modality"],
            value_col="value",
            filename=f"{remote_range_figure_filename.stem}_summary.csv",
        )
        self.plot_benchmark_slices_vs_time(
            df=remote_slice_and_read_pdf,
            metric_order=self.pynwb_read_order if order is None else order,
            y_value="total_time",  # includes file read + slice time
            filename=remote_read_figure_filename,
            caption=(
                "Performance trends as a function of data slice size. "
                "Data points indicate combined file open + slice times when streaming data remotely. "
                "A baseline value (slice size = 0) indicates the file open time alone."
            ),
            **plot_kwargs,
        )

        self.plot_benchmark_slices_vs_time(
            df=remote_slice_and_read_pdf,
            metric_order=self.pynwb_read_order if order is None else order,
            y_value="value",  # does not include file read time, only slice time
            filename=remote_range_figure_filename,
            caption=(
                "Performance trends as a function of data slice size. "
                "Data points include slice time only when streaming data remotely. "
            ),
            **plot_kwargs,
        )

        # get local read + slice times combined (as if already downloaded the file)
        local_slice_and_read_df = db.combine_read_and_slice_times(
            read_col_name="time_local_file_reading", slice_col_name="time_local_slicing", with_baseline=True
        )
        local_slice_and_read_pdf = local_slice_and_read_df.collect().to_pandas()
        self._write_summary_table(
            df=local_slice_and_read_pdf,
            group_cols=["slice_number", "is_preloaded", "benchmark_name_clean", "modality"],
            value_col="total_time",
            filename=f"{local_read_figure_filename.stem}_summary.csv",
        )
        self.plot_benchmark_slices_vs_time(
            df=local_slice_and_read_pdf,
            metric_order=None,
            y_value="total_time",  # includes file read + slice time
            filename=local_read_figure_filename,
            caption=(
                "Performance trends as a function of data slice size. "
                "Data points indicate combined file open + slice times when accessing local data. "
                "This is the expected times as if the file has already been downloaded. "
                "A baseline value (slice size = 0) indicates the file open time alone."
            ),
            **plot_kwargs,
        )

        # Generate linear extrapolation plots showing intersection points
        # get download + local read + slice (need to download full file and then open and read)
        download_slice_and_read_df = db.combine_download_read_and_slice_times(
            read_col_name="time_local_file_reading", slice_col_name="time_local_slicing", with_baseline=True
        )
        download_slice_and_read_pdf = download_slice_and_read_df.collect().to_pandas()
        self._write_summary_table(
            df=download_slice_and_read_pdf,
            group_cols=["slice_number", "is_preloaded", "benchmark_name_clean", "modality"],
            value_col="total_time",
            filename=f"{extrapolation_figure_filename.stem}_download_summary.csv",
        )
        self.plot_benchmark_slice_extrapolations(
            stream_df=remote_slice_and_read_df,
            download_df=download_slice_and_read_df,
            filename=extrapolation_figure_filename,
            caption=(
                "Linear extrapolation comparing streaming vs. download approaches. "
                "Solid lines show streaming performance (remote open + slice), dashed lines show download performance (download + local open + slice). "
                "X markers indicate crossover points where downloading becomes faster than streaming. "
                "The x-axis represents the number of data slices, helping determine when to download vs. stream data. "
                "Note that some extrapolations are not included because they did not have intersection points in the positive quadrant. "
                "This often occurs if the difference in slice range times in small and not monotonically increasing."
            ),
            **plot_kwargs,
        )

    def plot_benchmark_slice_extrapolations(
        self,
        stream_df: pl.LazyFrame,
        download_df: pl.LazyFrame,
        group: str = "benchmark_name_clean",
        filename: Path = None,
        row: Optional[str] = None,
        sharex: bool = True,
        caption: str = None,
    ):
        """Plot linear extrapolations showing streaming vs download crossover points."""
        collected_download = download_df.collect()
        collected_stream = stream_df.collect()

        if collected_download.is_empty():
            self._record_skipped_output("plot", filename, "No download/local data available to plot.")
            return

        # Get unique modalities and row values for subplot layout
        modalities = sorted(collected_download.select("modality").unique().to_series().to_list())
        row_values = sorted(collected_download.select(row).unique().to_series().to_list()) if row else [None]
        benchmarks = sorted(collected_stream.select(group).unique().to_series().to_list())

        # Create mappings for plot
        hdf5_colors = iter(sns.color_palette("Greens", n_colors=len([b for b in benchmarks if b.startswith("hdf5")])))
        zarr_colors = iter(sns.color_palette("Reds", n_colors=len([b for b in benchmarks if b.startswith("zarr")])))
        lindi_colors = iter(sns.color_palette("Blues", n_colors=len([b for b in benchmarks if b.startswith("lindi")])))
        modality_to_col = {mod: i for i, mod in enumerate(modalities)}
        row_to_row = {rv: i for i, rv in enumerate(row_values)}
        benchmarks_to_color = {}
        for bm in benchmarks:
            if bm.startswith("hdf5"):
                benchmarks_to_color[bm] = next(hdf5_colors)
            elif bm.startswith("zarr"):
                benchmarks_to_color[bm] = next(zarr_colors)
            else:
                benchmarks_to_color[bm] = next(lindi_colors)

        # Create subplots
        fig, axes = plt.subplots(nrows=len(row_values), ncols=len(modalities), figsize=(15, 10), squeeze=False)

        # Original loop structure
        for (modality, benchmark_name, is_preloaded), remote_group in collected_stream.group_by(
            ["modality", group, row]
        ):
            format_family = benchmark_name.split(" ")[0]
            local_group = download_df.filter(
                (pl.col("modality") == modality)
                & (pl.col("format_family") == format_family)
                & (pl.col(row) == is_preloaded)
            ).collect()
            # TODO - for all modalities (specifically icephys) add an additional figure that takes the longest slice range and multiply those times

            if not local_group.is_empty():
                # Determine which axis to use based on modality and row value
                col_idx = modality_to_col[modality]
                row_idx = row_to_row[is_preloaded]
                color = benchmarks_to_color[benchmark_name]

                # Plot the extrapolation
                self.plot_linear_extrapolation_with_intersection(
                    remote_group=remote_group,
                    local_group=local_group,
                    benchmark_name=benchmark_name,
                    ax=axes[row_idx, col_idx],
                    color=color,
                    title=f"is_preloaded={is_preloaded} | modality = {modality}",
                )

        axes[0, 0].legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)

        # Add figure caption
        caption = self._add_environment_caption(caption)
        fig.text(0.5, -0.01, caption, ha="center", va="top", fontsize=9, wrap=True, style="italic")

        sns.despine()
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches="tight")
        plt.close()

    def plot_method_rankings(self, db: BenchmarkDatabase):
        """Create heatmap showing method rankings across benchmarks."""
        print("Plotting method rankings heatmap...")

        slice_df = db.filter_tests("time_remote_slicing")
        read_df = db.filter_tests("time_remote_file_reading")
        read_h5py_df = read_df.filter(pl.col("benchmark_name_clean").is_in(self.file_open_order))
        read_pynwb_df = read_df.filter(pl.col("benchmark_name_clean").is_in(self.pynwb_read_order))
        slice_largest_df = slice_df.filter(pl.col("benchmark_name_clean").is_in(self.pynwb_read_order)).filter(
            pl.col("slice_number") == 5
        )
        slice_largest_not_preloaded_df = slice_largest_df.filter(pl.col("is_preloaded") == False)
        slice_largest_preloaded_df = slice_largest_df.filter(pl.col("is_preloaded") == True)

        self._write_summary_table(
            df=read_h5py_df.collect().to_pandas(),
            group_cols=["benchmark_name_type", "benchmark_name_clean", "modality"],
            value_col="value",
            filename=f"method_rankings_heatmap_remote_file_open{self.environment_filename_postfix}_summary.csv",
        )
        self._write_summary_table(
            df=read_pynwb_df.collect().to_pandas(),
            group_cols=["benchmark_name_type", "benchmark_name_clean", "modality"],
            value_col="value",
            filename=f"method_rankings_heatmap_remote_file_open_pynwb{self.environment_filename_postfix}_summary.csv",
        )
        self._write_summary_table(
            df=slice_largest_not_preloaded_df.collect().to_pandas(),
            group_cols=["benchmark_name_type", "slice_number", "is_preloaded", "benchmark_name_clean", "modality"],
            value_col="value",
            filename=f"method_rankings_heatmap_remote_slicing_not_preloaded_largest_range{self.environment_filename_postfix}_summary.csv",
        )
        self._write_summary_table(
            df=slice_largest_preloaded_df.collect().to_pandas(),
            group_cols=["benchmark_name_type", "slice_number", "is_preloaded", "benchmark_name_clean", "modality"],
            value_col="value",
            filename=f"method_rankings_heatmap_remote_slicing_preloaded_largest_range{self.environment_filename_postfix}_summary.csv",
        )

        fig, axes = plt.subplots(4, 1, figsize=(8, 20))
        axes[0] = self.plot_benchmark_heatmap(
            df=read_h5py_df,
            metric_order=self.file_open_order,
            ax=axes[0],
            title="Remote File Opening",
            vmin=0,
            vmax=4,
        )
        axes[1] = self.plot_benchmark_heatmap(
            df=read_pynwb_df,
            metric_order=self.pynwb_read_order,
            ax=axes[1],
            title="Remote File Opening - PyNWB",
            vmin=0,
            vmax=200,
        )
        # plot only largest slice range for clarity, separated by preload condition
        axes[2] = self.plot_benchmark_heatmap(
            df=slice_largest_not_preloaded_df,  # NOTE - if updating, also update caption in plot_benchmark_heatmap
            metric_order=self.pynwb_read_order,
            ax=axes[2],
            title="Remote Slicing - Not Preloaded",
            vmin=0,
            vmax=10,
        )
        axes[3] = self.plot_benchmark_heatmap(
            df=slice_largest_preloaded_df,  # NOTE - if updating, also update caption in plot_benchmark_heatmap
            metric_order=self.pynwb_read_order,
            ax=axes[3],
            title="Remote Slicing - Preloaded",
            vmin=0,
            vmax=10,
        )

        # Add figure caption
        caption = (
            f"Heatmap showing mean benchmark performance times (in seconds) across different data modalities. "
            "Each cell displays the average time for a specific method-modality combination. "
            "Methods are shown in a fixed logical order for consistent comparison across panels. "
            "Stars (*) indicate the fastest method for each modality. "
            "For remote slicing, only the largest slice range was used to compute the averages, "
            "and preloaded and non-preloaded benchmark conditions are shown separately."
        )
        caption = self._add_environment_caption(caption)
        fig.text(0.5, -0.01, caption, ha="center", va="top", fontsize=9, wrap=True, style="italic")

        plt.tight_layout()
        plt.savefig(self.output_directory / self._filename_with_environment_postfix("method_rankings_heatmap"), dpi=300)
        plt.close()

    def plot_performance_across_versions(
        self,
        db: BenchmarkDatabase,
        order: List[str] = None,
        hue: str = "benchmark_name_clean",
        benchmark_type: str = "time_remote_file_reading",
    ):
        """Plot performance changes over time for a given benchmark type."""
        print(f"Plotting performance over time")

        df = db.filter_results_for_environment_timepoints()
        df = (
            df.filter(pl.col("benchmark_name_type") == benchmark_type)
            .filter(pl.col("benchmark_name_clean").is_in(self.pynwb_read_order))
            .collect()
            .to_pandas()
        )

        if df.empty:
            self._record_skipped_output(
                "plot", self.output_directory / f"performance_over_{benchmark_type}.pdf", "No data available to plot."
            )
            return

        summary_group_cols = [
            "benchmark_name_type",
            "environment_timepoint",
            "package_name",
            "package_version",
            "benchmark_name_clean",
            "modality",
        ]
        if benchmark_type == "time_remote_slicing":
            summary_group_cols.append("is_preloaded")
        self._write_summary_table(
            df=df,
            group_cols=summary_group_cols,
            value_col="value",
            filename=f"performance_over_{benchmark_type}_summary.csv",
        )

        method_order = self.pynwb_read_order if order is None else order
        g = sns.catplot(
            data=df,
            x="environment_timepoint",
            y="value",
            col="modality",
            row="is_preloaded" if benchmark_type == "time_remote_slicing" else None,
            hue="benchmark_name_clean",
            hue_order=method_order,
            order=sorted(df["environment_timepoint"].unique()),
            sharex=True,
            palette="Paired",
            sharey=False,
            kind="point",
        )
        if g._legend is not None:
            display_labels = dict(zip(method_order, self._display_method_labels(method_order)))
            for text in g._legend.texts:
                text.set_text(display_labels.get(text.get_text(), text.get_text()))
        g.set(xlabel="Environment timepoint", ylabel="Time (s)")

        # Add figure caption
        caption = (
            "Performance trends across different software environment versions over time. "
            "Each line represents a different method, showing how execution time changes as dependencies are updated. "
            "Key dependencies of interest were fixed and environments with YYYY-06-30 timepoints were generated programmatically. "
            "See the _package_versions utility script for further details."
            "Note that the 2025-09-01 timepoint is an estimate for approximately when the latest environment was generated. "
        )
        g.figure.text(0.5, -0.01, caption, ha="center", va="top", fontsize=9, wrap=True, style="italic")

        sns.despine()
        plt.savefig(self.output_directory / f"performance_over_{benchmark_type}.pdf", dpi=300, bbox_inches="tight")
        plt.close()

    def _plot_environment_specific_figures(self, db: BenchmarkDatabase):
        """Generate all plots that should be scoped to one environment context."""

        # # 1. WHICH LIBRARY SHOULD I USE TO STREAM DATA
        # Remote file reading / slicing benchmarks
        self.plot_read_benchmarks(db, suffix="_pynwb")
        self.plot_read_benchmarks(db, order=self.file_open_order, suffix="")
        self.plot_slice_benchmarks(db)

        # Network tracking analysis
        benchmark_type = "network_tracking_remote_file_reading"
        self.plot_read_benchmarks(
            db, order=self.file_open_order, benchmark_type=benchmark_type, network_tracking=True, suffix=""
        )
        self.plot_read_benchmarks(db, benchmark_type=benchmark_type, network_tracking=True, suffix="_pynwb")
        self.plot_slice_benchmarks(db, benchmark_type="network_tracking_remote_slicing", network_tracking=True)

        # Method rankings
        self.plot_method_rankings(db)

        # 2. WHEN TO DOWNLOAD VS. STREAM DATA?
        # baseline download line + time to open + slice locally vs. number of slices
        # time to open + slice locally vs. number of slices
        self.plot_download_vs_stream_benchmarks(db)

    def plot_all(self, db: BenchmarkDatabase, environment_timepoints: Optional[Dict[str, str]] = None):
        """Generate all benchmark visualization plots."""
        environment_timepoints = environment_timepoints or ENVIRONMENT_TIMEPOINTS
        environment_dates = list(environment_timepoints.keys())
        self.copy_environment_details(db, environment_timepoints=environment_timepoints)

        # Generate ordinary plots for all configured environments together.
        configured_environment_ids = list(environment_timepoints.values())
        all_environment_db = db.with_environment_ids(configured_environment_ids)
        self._set_environment_output_context("all", environment_caption_dates=environment_dates)
        print(f"\nStarting ordinary plot generation for environment context: all ({', '.join(environment_dates)})")
        self._plot_environment_specific_figures(all_environment_db)
        self.plot_network_runtime_correlations(all_environment_db)
        print("Finished ordinary plot generation for environment context: all")

        # Generate ordinary plots separately for each configured environment timepoint.
        for environment_date, environment_id in environment_timepoints.items():
            environment_db = db.with_environment_id(environment_id)
            self._set_environment_output_context(environment_date, environment_caption_dates=[environment_date])
            print(f"\nStarting ordinary plot generation for environment date: {environment_date}")
            self._plot_environment_specific_figures(environment_db)
            print(f"Finished ordinary plot generation for environment date: {environment_date}")

        # 3. HOW DOES PERFORMANCE CHANGE ACROSS VERSIONS/TIME
        # Performance-over-time plots span all configured environments and remain at the root output directory.
        self._set_environment_output_context(None)
        print("\nStarting performance-over-time plot generation across all configured environments")
        self.plot_performance_across_versions(db, benchmark_type="time_remote_file_reading")
        self.plot_performance_across_versions(db, benchmark_type="time_remote_slicing")
        print("Finished performance-over-time plot generation")
        self._write_skipped_outputs_report()
        print(f"Skipped-output report written to {self._base_output_directory / 'skipped_outputs.txt'}")
