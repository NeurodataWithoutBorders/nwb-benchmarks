import pathlib

from .setup import get_benchmarks_home_directory

MACHINE_FILE_VERSION = "1.4.1"
DATABASE_VERSION = "5.0.0"

HOME_DIR = get_benchmarks_home_directory()
RESULTS_DIR = HOME_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)
ENVIRONMENTS_DIR = HOME_DIR / "environments"
ENVIRONMENTS_DIR.mkdir(exist_ok=True)
MACHINES_DIR = HOME_DIR / "machines"
MACHINES_DIR.mkdir(exist_ok=True)
LOGS_DIR = HOME_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
