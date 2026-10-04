Running the Benchmarks
======================

Before running the benchmark suite, please ensure you are not running any additional heavy processes in the background to avoid interference or bottlenecks.

Also, please ensure prior to running the benchmark that all code changes have been committed to your local branch.

For the most stable results, only run the benchmarks on the ``main`` branch.

To run the full benchmark suite, including network tracking tests (which require ``sudo`` on Mac and Linux platforms due to the
use of `psutil net_connections <https://psutil.readthedocs.io/en/latest/#psutil.net_connections>`_), first determine which network
interface you want to monitor (e.g., ``en0``, ``eth0``, etc.). You can typically find this information via your system settings,
or by running commands like ``ifconfig`` or ``ip addr`` in your terminal. On Linux/MacOS, this command will return the default
network interface name for internet connectivity:

.. code-block::

    route get default | awk '/interface:/{print $NF}'

On Windows, in Powershell, you can use:

.. code-block::

    Get-NetAdapter | Where-Object {$_.Status -eq "Up"}

and select the appropriate interface name from the output.

Then, set the environment variable ``NWB_BENCHMARKS_NETWORK_INTERFACE`` to the desired network interface.
For example, in a Unix-like terminal (Linux or macOS), you can do:

.. code-block::

    export NWB_BENCHMARKS_NETWORK_INTERFACE=en0

On Windows, you can use:

.. code-block::

    $env:NWB_BENCHMARKS_NETWORK_INTERFACE="Ethernet"

On Windows, or if ``tshark`` is not installed on the path, you may also need to set the ``TSHARK_PATH`` environment
variable to the absolute path to the ``tshark`` executable (e.g., ``tshark.exe``) on your system.

Then, simply call...

.. code-block::

    sudo -E nwb_benchmarks run

Or drop the ``sudo`` if on Windows.

Many of the current tests can take several minutes to complete; the entire suite will take many times that. Grab some coffee, read a book, or better yet (when the suite becomes larger) just leave it to run overnight.


Additional Flags
----------------

Subset of the Suite
~~~~~~~~~~~~~~~~~~~

To run only a single benchmark suite or a single case within a benchmark, use the command...

.. code-block::

    nwb_benchmarks run --bench <benchmark file stem or module.class.test function names>

For example,

.. code-block::

    nwb_benchmarks run --bench time_remote_file_reading.HDF5H5pyFileReadBenchmark.time_read_hdf5_h5py_remfile_no_cache

Debug mode
~~~~~~~~~~

If you want to get a full traceback to examine why a new test might be failing, simply add the flag...

.. code-block::

    nwb_benchmarks run --debug

Setting this flag will also override the ``repeat`` parameter of benchmarks and set it to 1, so that you can quickly
iterate on the code and see the results of your changes without having to wait for the full suite to run.

Setting this flag will also skip the reminder about contributing results, since debug runs are not meant to be shared.

Contributing Results
--------------------

Each successful ``nwb_benchmarks run`` writes three kinds of JSON files under ``~/.nwb_benchmarks``:

* ``results/`` holds the measurements of each run,
* ``machines/`` and ``environments/`` hold the hardware and package descriptions the results refer to (written
  once per unique configuration).

Results from all contributors are collected in the central
`nwb-benchmarks-results <https://github.com/NeurodataWithoutBorders/nwb-benchmarks-results>`_ repository, which
mirrors these three folders. There are two ways to get your files there.

Automated runs
~~~~~~~~~~~~~~

Machines that run the suite regularly should be registered as self-hosted GitHub Actions runners of the
`nwb-benchmarks-runner <https://github.com/CodyCBakerPhD/nwb-benchmarks-runner>`_ repository. Its scheduled
workflows run the suite, then commit the new files to the central repository using a token that you provide, so
results can be contributed by many people without sharing credentials. See that repository's README for the
setup steps.

Manual contribution
~~~~~~~~~~~~~~~~~~~

For one-off runs, open a pull request against the central repository:

.. code-block::

    <Fork https://github.com/NeurodataWithoutBorders/nwb-benchmarks-results on GitHub>
    git clone https://github.com/<your GitHub username>/nwb-benchmarks-results
    cd nwb-benchmarks-results
    git checkout -b new_results_from_<...>
    cp ~/.nwb_benchmarks/results/*.json results/
    cp ~/.nwb_benchmarks/machines/*.json machines/
    cp ~/.nwb_benchmarks/environments/*.json environments/
    git add results machines environments
    git commit -m "New results from ...."
    git push

Then, open a PR to merge the results to the ``main`` branch of the central repo.

.. note::

    When running tests with ``sudo`` the new results may be owned by ``root``. To avoid having to run pre-commit hooks
    in sudo you may need to change the owner of the results first, e.g., via ``sudo chown -R <new_owner> ~/.nwb_benchmarks``.

.. note::

    Each result file should be single to double-digit KB in size; if we ever reach the point where this is prohibitive to store on GitHub itself, then we will investigate other upload strategies and purge the folder from the repository history.


Generating Figures from Results
--------------------------------

Once benchmark results have been collected (either from your own runs or from the central results repository), you can generate
figures to visualize the performance data.

To generate all figures with default settings:

.. code-block::

    nwb_benchmarks generate_figures

This will:

1. Automatically clone or use the cached `nwb-benchmarks-results <https://github.com/NeurodataWithoutBorders/nwb-benchmarks-results>`_ repository in the default path ``~/.cache/nwb-benchmarks/nwb-benchmarks-results``
2. Process the benchmark results into a parquet file
3. Generate all visualization figures in a ``./figures/`` directory in your current working directory


You can specify additional options such as a custom benchmarks results directory or output directory as follows:


.. code-block::

    nwb_benchmarks generate_figures --output-dir /path/to/output --results-dir /path/to/results

Note that older results are excluded by default to focus on performance data after some updates to the benchmarks test suite.
You can override this behavior using the following flag with a custom date: ``--exclude-older YYYY-MM-DD``.
