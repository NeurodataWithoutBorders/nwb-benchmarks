import nwb_benchmarks.core

# `nwb_benchmarks.benchmarks.params` resolves the redirected DANDI URLs through the DANDI API when it is imported. Stub
# the lookup before any test imports the benchmark suite, so the unit tests run offline and do not depend on the API.
nwb_benchmarks.core.get_https_url = lambda dandiset_id, dandi_path, follow_redirects=1: (
    f"https://example.invalid/{dandiset_id}/{dandi_path}"
)
