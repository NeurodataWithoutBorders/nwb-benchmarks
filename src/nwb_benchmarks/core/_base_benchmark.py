class BaseBenchmark:
    """Base class for NWB benchmarks."""

    # ASV timing controls used by all benchmarks that inherit from this base class.
    #
    # rounds:
    #     Number of independent timing rounds ASV performs for each benchmark/parameter
    #     combination. Keeping this at 1 avoids rerunning expensive remote setup/timing
    #     sequences more than necessary.
    #
    # repeat:
    #     Number of samples collected within each round. Each sample invokes the timed
    #     benchmark according to ``number`` below. Increase this when more repeated
    #     measurements are needed for noisy benchmarks.
    #
    # number:
    #     Number of times ASV calls the timed benchmark function per sample before
    #     reporting the average time per call. ASV's default is 0, which means
    #     auto-calibrate this value to fill a minimum sample time. For remote-access
    #     benchmarks this can be misleading: after the first call, libraries such as
    #     h5py may serve repeated reads from in-memory decompressed chunk caches, so an
    #     auto-selected ``number > 1`` can mostly measure cache hits rather than the
    #     intended remote read/decompression cost. Use ``number = 1`` so each reported
    #     sample corresponds to exactly one timed call.
    #
    # warmup_time:
    #     Seconds ASV spends warming up before collecting samples. Keep this at 0.0 so
    #     cache-sensitive remote-access benchmarks do not get warmed into a cached state
    #     before measurement.
    rounds = 1
    repeat = 1
    number = 1
    warmup_time = 0.0
