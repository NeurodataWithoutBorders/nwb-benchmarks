import textwrap
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import seaborn as sns
from packaging import version

from nwb_benchmarks.database._processing import BenchmarkDatabase

DEFAULT_BENCHMARK_ORDER = [
    "hdf5 h5py remfile no cache",
    "hdf5 h5py fsspec https no cache",
    "hdf5 h5py fsspec s3 no cache",
    "hdf5 h5py remfile with cache",
    "hdf5 h5py fsspec https with cache",
    "hdf5 h5py fsspec s3 with cache",
    "hdf5 h5py ros3",
    "lindi h5py",
    "zarr s3",
    "zarr s3 force no consolidated",
]

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
        self._setup_matplotlib()

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

    def _add_mean_std_annotations(self, value: str, group: str, order: List[str], **kwargs):
        """Add mean ± std annotations to plot."""
        stats_df = kwargs.get("data").groupby(group)[value].agg(["mean", "std", "max", "count"])

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
            warnings.warn(f"No data available for summary table {filename}. Skipping table.")
            return

        missing_cols = [col for col in [*group_cols, value_col] if col not in df.columns]
        if missing_cols:
            warnings.warn(f"Cannot write summary table {filename}; missing columns: {missing_cols}.")
            return

        summary_df = (
            df.groupby(group_cols, dropna=False)[value_col]
            .agg(n="count", mean="mean", median="median", std="std", min="min", max="max")
            .reset_index()
        )
        summary_df.to_csv(self.summary_tables_directory / filename, index=False)

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
            warnings.warn(f"No data available to plot for benchmark heatmap. Skipping plot.")
            return

        # Create heatmap dataframe (which will compute order if not provided)
        heatmap_df = self._create_heatmap_df(collected_df, group, metric_order, aggfunc=aggfunc)

        if ax is None:
            _, ax = plt.subplots(figsize=(10, 8))

        sns.heatmap(data=heatmap_df, annot=True, fmt=".3g", cmap="OrRd", ax=ax, vmin=vmin, vmax=vmax)
        ax.set(xlabel="", ylabel="")

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
            warnings.warn(f"Warning: No data available to plot for {filename}. Skipping plot.")
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

        # Add figure caption
        if kind == "strip" and caption is not None:
            caption += "Each point represents a single benchmark run. "
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
            warnings.warn(f"Warning: No data available to plot for {filename}. Skipping plot.")
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
            g.figure.text(0.5, -0.01, caption, ha="center", va="top", fontsize=9, wrap=True, style="italic")

        # Add intersection annotations
        if intersections_df is not None:
            g.map_dataframe(self._add_annotations_df, intersections_df=intersections_df, order=metric_order)

        g.set(xlabel="Relative slice size", ylabel="Time (s)")
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
        print(f"Plotting read benchmarks for {benchmark_type}...")

        filtered_df = db.filter_tests(benchmark_type).collect()
        prefix = self._get_filename_prefix(network_tracking)

        # Create base plot kwargs
        caption_suffix = " using pynwb. " if suffix == "_pynwb" else ". "
        caption = (
            f"Benchmark execution times across different methods and modalities{caption_suffix}"
            "Text annotations, if present, display mean ± standard deviation and sample size (n). "
        )
        figure_filename = self.output_directory / f"{prefix}file_open{suffix}.pdf"
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
                "filename": self.output_directory / f"{prefix}file_open_scatter{suffix}.pdf",
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
                    filename=f"{prefix}slicing_{preload_label}_summary.csv",
                )

                for slice_num, slice_df in enumerate(preload_df.partition_by("slice_number")):
                    figure_filename = self.output_directory / f"{prefix}slicing_{preload_label}_range{slice_num}.pdf"
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
                        "filename": self.output_directory / f"{prefix}slicing_{preload_label}_scatter.pdf",
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
            filename=f"{prefix}slicing_summary.csv",
        )

        # Plot box plot for each slice value
        for slice_num, slice_df in enumerate(base_kwargs["df"].partition_by("slice_number")):
            figure_filename = self.output_directory / f"{prefix}slicing_range{slice_num}.pdf"
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
                "filename": self.output_directory / f"{prefix}slicing_scatter.pdf",
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
        ax.plot(x_range, y_remote, color=color, linestyle="solid", linewidth=2, label=f"{benchmark_name}")
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
        remote_read_figure_filename = Path(f"{base_filename}_with_remote_read.pdf")
        remote_range_figure_filename = Path(f"{base_filename}_range.pdf")
        local_read_figure_filename = Path(f"{base_filename}_with_local_read.pdf")
        extrapolation_figure_filename = Path(f"{base_filename}_with_extrapolation.pdf")
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
            warnings.warn(f"Warning: No data available to plot for {filename}. Skipping plot.")
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
            filename="method_rankings_heatmap_remote_file_open_summary.csv",
        )
        self._write_summary_table(
            df=read_pynwb_df.collect().to_pandas(),
            group_cols=["benchmark_name_type", "benchmark_name_clean", "modality"],
            value_col="value",
            filename="method_rankings_heatmap_remote_file_open_pynwb_summary.csv",
        )
        self._write_summary_table(
            df=slice_largest_not_preloaded_df.collect().to_pandas(),
            group_cols=["benchmark_name_type", "slice_number", "is_preloaded", "benchmark_name_clean", "modality"],
            value_col="value",
            filename="method_rankings_heatmap_remote_slicing_not_preloaded_largest_range_summary.csv",
        )
        self._write_summary_table(
            df=slice_largest_preloaded_df.collect().to_pandas(),
            group_cols=["benchmark_name_type", "slice_number", "is_preloaded", "benchmark_name_clean", "modality"],
            value_col="value",
            filename="method_rankings_heatmap_remote_slicing_preloaded_largest_range_summary.csv",
        )

        fig, axes = plt.subplots(4, 1, figsize=(8, 20))
        axes[0] = self.plot_benchmark_heatmap(
            df=read_h5py_df,
            ax=axes[0],
            title="Remote File Opening",
            vmin=0,
            vmax=4,
        )
        axes[1] = self.plot_benchmark_heatmap(
            df=read_pynwb_df,
            ax=axes[1],
            title="Remote File Opening - PyNWB",
            vmin=0,
            vmax=200,
        )
        # plot only largest slice range for clarity, separated by preload condition
        axes[2] = self.plot_benchmark_heatmap(
            df=slice_largest_not_preloaded_df,  # NOTE - if updating, also update caption in plot_benchmark_heatmap
            ax=axes[2],
            title="Remote Slicing - Not Preloaded",
            vmin=0,
            vmax=10,
        )
        axes[3] = self.plot_benchmark_heatmap(
            df=slice_largest_preloaded_df,  # NOTE - if updating, also update caption in plot_benchmark_heatmap
            ax=axes[3],
            title="Remote Slicing - Preloaded",
            vmin=0,
            vmax=10,
        )

        # Add figure caption
        caption = (
            f"Heatmap showing mean benchmark performance times (in seconds) across different data modalities. "
            "Each cell displays the average time for a specific method-modality combination. "
            "The order is sorted by format type (lindi, zarr, hdf5) and then by average performance within each type. "
            "Stars (*) indicate the fastest method for each modality. "
            "For remote slicing, only the largest slice range was used to compute the averages, "
            "and preloaded and non-preloaded benchmark conditions are shown separately."
        )
        fig.text(0.5, -0.01, caption, ha="center", va="top", fontsize=9, wrap=True, style="italic")

        plt.tight_layout()
        plt.savefig(self.output_directory / "method_rankings_heatmap.pdf", dpi=300)
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
            warnings.warn(
                f"Warning: No data available to plot for performance_over_{benchmark_type}.pdf. Skipping plot."
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

        g = sns.catplot(
            data=df,
            x="environment_timepoint",
            y="value",
            col="modality",
            row="is_preloaded" if benchmark_type == "time_remote_slicing" else None,
            hue="benchmark_name_clean",
            hue_order=self.pynwb_read_order if order is None else order,
            order=sorted(df["environment_timepoint"].unique()),
            sharex=True,
            palette="Paired",
            sharey=False,
            kind="point",
        )
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

    def plot_all(self, db: BenchmarkDatabase):
        """Generate all benchmark visualization plots."""

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

        # 3. HOW DOES PERFORMANCE CHANGE ACROSS VERSIONS/TIME
        # performance on a single test (time to read/slice) vs. version (h5py, fsspec, etc.)
        self.plot_performance_across_versions(db, benchmark_type="time_remote_file_reading")
        self.plot_performance_across_versions(db, benchmark_type="time_remote_slicing")
