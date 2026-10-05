Writing Benchmarks
==================

Have an idea for how to speed up read or write from a local or remote NWB file?

This section explains how to write your own benchmark to prove it robustly across platforms, architectures, and environments.


Standard Prefixes
-----------------

Just like how ``pytest`` automatically detects and runs any function or method leading with the keyphrase ``test_``, AirSpeed Velocity runs timing tests for anything prefixed with ``time_``, tracks peak memory via prefix ``peakmem_``, custom values, such as our functions for network traffic, with ``track_`` (this must return the value being tracked), and many others. Check out the full listing in the `primary AirSpeed Velocity documentation <https://asv.readthedocs.io/en/stable/index.html>`_.

A single tracking function should perform only the minimal operations you wish to time. It is also capable of tracking only a single value. The philosophy for this is to avoid interference from cross-measurements; that is, the act of tracking memory of the operation may impact how much overall time it takes that process to complete, so you would not want to simultaneously measure both time and memory.

.. note::

    One caveat with using ``track_`` is that if you want it to return the custom values as ``samples`` similar to the timing tests, it must be wrapped in a dictionary with required outer keywords ``samples`` and ``number=None``.


Class Structure
---------------

A single benchmark suite is a file within the ``benchmarks`` folder. It contains one or more benchmark classes. It is not itself important that the word 'Benchmark' be in the name of the class; only the prefix on the function matters.

Every benchmark function has an attribute ``timeout`` which specified the most number of seconds the process has to complete, otherwise it will count as a failure. The global value for this is set in the ``.asv.conf.json`` file.

Similar to ``unittest.TestCase`` classes, all benchmark classes have ``setup`` and ``teardown`` methods. Set any values that need to be established before the main benchmark cases run as attributes on the instance during ``setup``; likewise, if you save anything to disk and you don't want it to persist, remove it in the ``teardown`` step.

Timing benchmarks have several special attributes, the most important of which are ``rounds`` and ``repeat``. All timing functions in a class can be repeated in round-robin fashion using ``rounds > 1``; the philsophy here is to 'average out' variation on the system over time and may not always be relevant to increase. Each function in a suite is repeated ``repeat`` number of times to get an estimate of the standard deviation of the operation. Every function in the suite has at most ``timout`` number of seconds to complete, otherwise it will count as a failure.

For timing functions, ``setup`` and ``teardown`` will be called before and after execution of every count of ``rounds`` and ``repeat`` for every tracking function (such as timing) in the class. ``setup`` should therefore be as light as possible since it will be repeated so often, though sometimes even a minimal setup can still take time (such as reading a large remote NWB file using a suboptimal method). In some cases, ``setup_cache`` is a method that can be defined, and runs only once per class to precompute some operation, such as the creation of a fake dataset for testing on local disk.

.. note::

    Be careful to assign objects fetched by operations within the tracking functions; otherwise, you may unintentionally track the garbage collection step triggered when the reference count of the return value reaches zero in the namespace. For relatively heavy I/O operations this can be non-negligible.

Finally, you can leverage ``params`` and ``param_names`` on all benchmark types to perform a structured iteration over many inputs to the operations. ``param_names`` is a list of length equal to the number of inputs you wish to pass to an operation. ``params`` is a list of lists; the outer list being of equal length to the number of inputs, and each inner list being equal in length to the number of different cases to iterate over.

.. note::

    This structure for ``params`` can be very inconvenient to specify; if you desire a helper function that would instead take a flat list of dictionaries to serve as keyword arguments for all the iteration cases, please request it on our issues board.

For more advanced details, refer to the `primary AirSpeed Velocity documentation <https://asv.readthedocs.io/en/stable/index.html>`_.


Philosophy
----------

In the spirit of PEP8, it was decided from PRs 12, 19, 20, and 21 and ensuing meetings that we should adopt an explicit functionally-based approach to structuring these classes and their methods. This will help make the project  much easier to understand for people outside the team and will even reduce the amount of time it takes our main developers to read benchmarks they have not seen before or have forgotten about over an extended period of time.

This approach means relying as little on inheritance and mixins as possible to reduce the amount of implicit knowledge required to understand a benchmark just by looking at it - instead, all instance methods of the benchmark class should be explicitly defined.

To reduce duplicated code, it is suggested to write standalone helper functions in the ``core`` submodule and then call those functions within the benchmarks. This does mean that some redirection is still required to understand exactly how a given helper function operates, but this was deemed worth it to keep the actual size of benchmarks from inflating.

An example of this philosophy in practice would be as follows. In this example we wish to test how long it takes to both read a small remote NWB file (from the ``https_url``) using the ``remfile`` method...

.. code-block:: python

    from nwb_benchmarks.core import read_hdf5_h5py_remfile_no_cache

    class HDF5H5pyFileReadBenchmark:
        params = (
            dict(
                name="EcephysTestCase",
                https_url=get_https_url(
                    dandiset_id="000717",
                    dandi_path="sub-npI3/sub-npI3_behavior+ecephys.nwb",
                ),
            ),
        )

        def time_read_hdf5_h5py_remfile_no_cache(self, params: dict[str, str]):
            """Read a remote HDF5 file using h5py and remfile without cache."""
            https_url = params["https_url"]
            self.file, self.bytestream = read_hdf5_h5py_remfile_no_cache(https_url=https_url)

as well as how long it takes to slice ~20 MB of data from the contents of a remote NWB file that has a large amount of series data...

.. code-block:: python

    from nwb_benchmarks.core import get_https_url, read_hdf5_pynwb_remfile_no_cache

    class HDF5PyNWBRemfileNoCacheContinuousSliceBenchmark:
        params = (
            dict(
                name="EcephysTestCase1",
                https_url=get_https_url(
                    dandiset_id="000717",
                    dandi_path="sub-npI3/sub-npI3_behavior+ecephys.nwb",
                ),
                object_name="ElectricalSeries",
                slice_range=(slice(0, 262_144), slice(0, 384)),  # 12 chunks
            ),
        )

        def setup(self, params: dict[str, str | Tuple[slice]]):
            https_url = params["https_url"]
            object_name = params["object_name"]

            self.nwbfile, self.io, self.file, self.bytestream = read_hdf5_pynwb_remfile_no_cache(https_url=https_url)
            self.neurodata_object = get_object_by_name(nwbfile=self.nwbfile, object_name=object_name)
            self.data_to_slice = self.neurodata_object.data

        def time_slice(self, params: dict[str, str | Tuple[slice]]):
            """Slice a range of a dataset in a remote NWB file."""
            slice_range = params["slice_range"]
            # Note: store as self._temp to avoid tracking garbage collection as well.
            self._temp = self.data_to_slice[slice_range]


Notice how the ``read_hdf5_pynwb_remfile_no_cache`` function (which reads an HDF5-backend ``pynwb.NWBFile`` object into memory using the ``remfile`` method) was used as both the main operation being timed in the first case, then reused in the ``setup`` of the second. By following the redirection of the function to its definition, we find it is itself a compound of another helper function for ``remfile`` usage...

.. code-block:: python

    # In nwb_benchmarks/core/_streaming.py

    def read_hdf5_h5py_remfile_no_cache(https_url: str) -> Tuple[h5py.File, remfile.File]:
        """Load the raw HDF5 file from an S3 URL using remfile without a cache; does not formally read the NWB file."""
        byte_stream = remfile.File(url=https_url)
        file = h5py.File(name=byte_stream)
        return (file, byte_stream)


    def read_hdf5_pynwb_remfile_no_cache(https_url: str) -> Tuple[pynwb.NWBFile, pynwb.NWBHDF5IO, h5py.File, remfile.File]:
        """Read an HDF5 NWB file from an S3 URL using remfile without a cache."""
        (file, byte_stream) = read_hdf5_h5py_remfile_no_cache(https_url=https_url)
        io = pynwb.NWBHDF5IO(file=file)
        nwbfile = io.read()
        return (nwbfile, io, file, byte_stream)

and so we managed to save ~5 lines of code for every occurrence of this logic in the benchmarks. Good choices of function names are critical to effectively communicating the actions being undertaken. Thorough annotation of signatures is likewise critical to understanding input/output relationships for these functions.


.. _network-tracking-benchmarks:


Writing a network tracking benchmark
------------------------------------

Functions that require network access ---such as reading a file from S3--- are often a black box, with functions in other libraries (e.g., ``h5py``, ``fsspec``, etc.) managing the access to the remote resources. The runtime performance of such functions is often inherently driven by how these functions utilize the network to access the resources. It is, hence, important that we can profile the network traffic that is being generated to better understand, e.g., the amount of data that is being downloaded and uploaded, the number of requests that are being sent/received, and others.

To simplify the implementation of benchmarks for tracking network statistics, we implemented in the ``nwb_benchmarks.core`` module various helper classes and functions. The network tracking functionality is designed to track the network traffic generated by the main Python process that our tests are running during a user-defined period of time. The ``network_activity_tracker`` context manager can be used to track the network traffic generated by the code within the context. A basic network benchmark, then looks as follows:

.. code-block:: python

    from nwb_benchmarks import TSHARK_PATH
    from nwb_benchmarks.core import network_activity_tracker
    import requests   # Only used here for illustration purposes

    class SimpleNetworkBenchmark:

        def track_network_activity_uri_request():
            with network_activity_tracker(tshark_path=TSHARK_PATH) as network_tracker:
                x = requests.get('https://nwb-benchmarks.readthedocs.io/en/latest/setup.html')
            return network_tracker.asv_network_statistics

In cases where a context manager may not be sufficient, we can alternatively use the ``NetworkTracker`` class directly to explicitly control when to start and stop the tracking.

.. code-block:: python

    from nwb_benchmarks import TSHARK_PATH
    from nwb_benchmarks.core import NetworkTracker
    import requests   # Only used here for illustration purposes

    class SimpleNetworkBenchmark:

        def track_network_activity_uri_request():
            tracker = NetworkTracker()
            tracker.start_network_capture(tshark_path=TSHARK_PATH)
            x = requests.get('https://nwb-benchmarks.readthedocs.io/en/latest/setup.html')
            tracker.stop_network_capture()
            return tracker.asv_network_statistics

By default, the ``NetworkTracker`` and ``network_activity_tracker`` track the network activity of the current process ID (i.e., ``os.getpid()``), but the PID to track can also be set explicitly if a different process needs to be monitored.
