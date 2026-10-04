import itertools

from ..setup import get_benchmarks_home_directory


def clean_results():
    # Imported here rather than at module level: `globals` imports `setup`, and `setup` imports
    # `globals` while collecting machine info, so `globals` must never be the first of the two to
    # be imported. Importing `setup` above guarantees the order.
    from ..globals import ENVIRONMENTS_DIR, LOGS_DIR, MACHINES_DIR, RESULTS_DIR

    # Left behind by versions that uploaded results to the retired web server
    upload_tracker_file_path = get_benchmarks_home_directory() / "upload_tracker.json"
    upload_tracker_file_path.unlink(missing_ok=True)

    for results_file_path in itertools.chain(
        RESULTS_DIR.rglob(pattern="*.json"),
        MACHINES_DIR.rglob(pattern="*.json"),
        ENVIRONMENTS_DIR.rglob(pattern="*.json"),
        LOGS_DIR.rglob(pattern="*.txt"),
    ):
        results_file_path.unlink(missing_ok=True)
