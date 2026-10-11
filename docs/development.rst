Development
===========

This section covers advanced implementation details for managing the operation of the AirSpeed Velocity testing suite.


Environment Setup
------------

To setup a development environment, use ``pip install -e . --group all`` to install all dependencies including those for development and testing.
This command will install all packages required for database management, figure generation, and dev testing.


Coding Style
------------

We use pre-commit and the pre-commit PR bot to automatically ensure usage of ``black`` and ``isort``. To setup pre-commit in your local environment, simply call...


.. code-block::

    pip install pre-commit
    pre-commit install

Otherwise, please ensure all signatures and returns are annotated using the ``typing`` module.

Writing thorough docstrings is encouraged; please follow the Numpy style.

Import and submodule structure follows ``scikit-learn`` standard.


Unit Tests
----------

The ``tests`` directory holds unit tests for the code around the benchmarks, such as the reduction of ASV results and
the helpers of the incremental slicing benchmarks. They run offline and do not run any benchmark. To run them...

.. code-block::

    pip install -e . --group test
    pytest tests

The CI runs them on every pull request, before the benchmark smoke test.


Customized Machine Header
-------------------------

The spirit of AirSpeed Velocity to track machine specific information that could be related to benchmark performance is admirable. By calling ``asv machine`` you can generate a file on your system located at ``~/.asv-machine.json`` which is then used to uniquely tag results from your device. However, the defaults from ``asv machine --yes`` is woefully minimal. One example of the output of this call was...

.. code-block:: json

    {
        "DESKTOP-QJKETS8": {
            "arch": "AMD64",
            "cpu": "",
            "machine": "DESKTOP-QJKETS8",
            "num_cpu": "8",
            "os": "Windows 10",
            "ram": ""
        },
        "version": 1
    }

Not only are many of the values outright missing, but the ones that are found are not sufficient to uniquely tie to performance. For example, ``num_cpu=8`` does not distinguish between 8 Intel i5 or i9 cores, and there's a big difference between those two generations.

Thankfully, system information like this is generally easy to grab from other Python built-ins or from the wonderful externally maintained platform-specific utilities package ``psutil``.

As such, the functions in ``nwb_benchmarks.setup`` extend this framework by automatically tracking as many persistent system configurations as can be tracked without being overly invasive. A call to these functions is exposed to the ``nwb_benchmarks setup`` entrypoint for easy command line usage, which simply runs ``asv machine --yes`` to generate defaults and then calls the custom configuration to modify the file.

``nwb_benchmarks run`` also checks on each run of the benchmark if the system configuration has changed. Reasons this might change are mainly the disk partitions (which can include external USB drives, which can have a big difference in performance compared to SSD and HDD plugged directly into the motherboard via PCI).

Note that all machine names are remapped to a randomly generated FriendlyWords-style name (e.g. ``HappySun``) to avoid leaking any personal information about the user or their device.


Customized Call to Run
----------------------

By default, AirSpeed Velocity was designed primarily for scientific computing projects to track their optimization over time as measured by commits on the repo. As such, the default call to ``asv run`` has a DevOps continuous integration flavor in that it tries to spin up a unique virtual environment over a defined version matrix (both Python and constituent dependencies) each time, do a fresh checkout and pull of the Git repo, and only records the statistics aggregated over the runs of that instance.

For this project, since our tests are a bit heavier despite using somewhat minimal code, we would wish to keep the valuable raw samples from each run. The virtual environment setup from AirSpeed Velocity can also run into compatability issues with different conda distributions and so we wish to maintain broader control over this aspect.

These are the justifications to defining our ``nwb_benchmarks run`` command which wraps ``asv run`` with the following flags: ``--python=same`` means 'run benchmarks within the current Python/Conda environment' (do not create a separate one), which requires us to be running already from within an existing clone of the Git repo, but nonetheless requires the commit hash of that to be specified explicitly with ``--commit-hash <hash>``, and finally ``--record-samples`` to store the values of each ``round`` and ``repeat``.

A successful run of the benchmark produces a ``.json`` file in the ``.asv/intermediate_results`` folder, as well as provenance records of the machine and benchmark state. The name of this JSON file is usually a combination of the name of the environment and the flags passed to ``asv run``, and is not necessarily guaranteed to be different over multiple runs on the same commit hash.


Customized Parsing of Results
-----------------------------

Since our first approach to simplifying the sharing of results is to just commit them to the common GitHub repo, it was noticed that the default results files stored a lot of extraneous information.

For example, here is an abridged example of the raw ASV output file...

.. code-block:: json

    {"commit_hash": "ee3c985d8acf4539fb41b015e85c07ceb928c71d", "env_name": "existing-pyD__anaconda3_envs_nwb_benchmarks_3_11_created_on_2_17_2024_python.exe", "date": 1708536830000, "params": <copy of .asv.machine.json contents>, "python": "3.11", "requirements": {}, "env_vars": {}, "result_columns": ["result", "params", "version", "started_at", "duration", "stats_ci_99_a", "stats_ci_99_b", "stats_q_25", "stats_q_75", "stats_number", "stats_repeat", "samples", "profile"], "results": {"time_remote_slicing.FsspecNoCacheContinuousSliceBenchmark.time_slice": [[12.422975199995562], [["'https://dandiarchive.s3.amazonaws.com/blobs/fec/8a6/fec8a690-2ece-4437-8877-8a002ff8bd8a'"], ["'ElectricalSeriesAp'"], ["(slice(0, 30000, None), slice(0, 384, None))"]], "bb6fdd6142015840e188d19b7e06b38dfab294af60a25c67711404eeb0bc815f", 1708552612283, 59.726, [-22.415], [40.359], [6.5921], [13.078], [1], [3], [[0.8071024999953806, 0.9324163000565022, 0.5638924000086263]]], "time_remote_slicing.RemfileContinuousSliceBenchmark.time_slice": [[0.5849523999495432], [["'https://dandiarchive.s3.amazonaws.com/blobs/fec/8a6/fec8a690-2ece-4437-8877-8a002ff8bd8a'"], ["'ElectricalSeriesAp'"], ["(slice(0, 30000, None), slice(0, 384, None))"]], "f9c77e937b6e41c5a75803e962cc9a6f08cb830f97b04f7a68627a07fd324c11", 1708552672010, 10.689, [0.56549], [0.60256], [0.58225], [0.58626], [1], [3], [[0.5476778000593185, 8.321383600006811, 9.654714399948716]]]}, "durations": {}, "version": 2}

This structure is both hard to read due to no indentation, poorly self-annotated due to everything being JSON arrays instead of objects with representative names, and there are a large number of values here that we don't really care about.

Since all we're after here is the raw tracking output, some custom reduction of the original results files is performed so that only the minimal amount of information needed is actually stored in the final results files. These parsed results follow the dandi-esque name pattern ``result_timestamp-%Y-%M-%D-%H-%M-%S_machine-<machine hash>_environment-<environment hash>.json`` and are stored in the outer level ``results`` folder along with some ``info_machine-<machine hash>`` and ``info_environment-<environment hash>`` header files that are not regenerated whenever the hashes are the same.

The same file reduced then appears as...

.. code-block:: json

    {
        "version": 2,
        "timestamp": "2024-02-21-12-33-50",
        "commit_hash": "ee3c985d8acf4539fb41b015e85c07ceb928c71d",
        "environment_hash": "246cf6a886d9a66a9b593d52cb681998fab55adf",
        "machine_hash": "e109d91eb8c6806274a5a7909c735869415384e9",
        "results": {
            "time_remote_slicing.FsspecNoCacheContinuousSliceBenchmark.time_slice": {
                "(\"'https://dandiarchive.s3.amazonaws.com/blobs/fec/8a6/fec8a690-2ece-4437-8877-8a002ff8bd8a'\", \"'ElectricalSeriesAp'\", '(slice(0, 30000, None), slice(0, 384, None))')": [
                    0.8071024999953806,
                    0.9324163000565022,
                    0.5638924000086263
                ]
            },
            "time_remote_slicing.RemfileContinuousSliceBenchmark.time_slice": {
                "(\"'https://dandiarchive.s3.amazonaws.com/blobs/fec/8a6/fec8a690-2ece-4437-8877-8a002ff8bd8a'\", \"'ElectricalSeriesAp'\", '(slice(0, 30000, None), slice(0, 384, None))')": [
                    0.5476778000593185,
                    8.321383600006811,
                    9.654714399948716
                ]
            }
        }
    }

which is also indented for improved human readability and line-by-line GitHub tracking. This indentation adds about 50 bytes per kilobyte compared to no indentation.

.. note::

    If this ``results`` folder eventually becomes too large for Git to reasonably handle, we will explore options to share via other data storage services.


.. include:: network_tracking.rst
