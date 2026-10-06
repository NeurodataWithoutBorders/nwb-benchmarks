from nwb_benchmarks import RUN_INCREMENTAL_SLICING_BENCHMARK_MODALITIES

# The DANDI API download URLs in this module (`https_url_no_redirect`) are literals, resolved once with
# `nwb_benchmarks.core.get_https_url(..., follow_redirects=False)`, so that importing the benchmark suite, which ASV does
# in every process it starts, does not look every asset up through the DANDI API. The S3 locations those URLs redirect
# to (`https_url_redirected`) are storage details rather than a stable interface, so they are still resolved at import
# with `follow_redirects=1`. The CI workflow checks that the literals still match what the DANDI API resolves to
# (`python -m nwb_benchmarks.scripts.check_dandi_urls`); if an asset is replaced on DANDI, run that script and update
# the URLs it reports.
from nwb_benchmarks.core import get_https_url

################################### BASE PARAMETERS ###################################
hdf5_ecephys_params = dict(
    dandiset_id="000717",
    dandi_path="sub-npI3/sub-npI3_behavior+ecephys.nwb",
)
hdf5_ecephys_params["https_url_redirected"] = get_https_url(
    hdf5_ecephys_params["dandiset_id"], hdf5_ecephys_params["dandi_path"], follow_redirects=1
)
hdf5_ecephys_params["https_url_no_redirect"] = (
    "https://api.dandiarchive.org/api/assets/df0e074e-3509-4b03-908e-2a1303072707/download/"
)

hdf5_ophys_params = dict(
    dandiset_id="000717",
    dandi_path="sub-R6/sub-R6_behavior+ophys.nwb",
)
hdf5_ophys_params["https_url_redirected"] = get_https_url(
    hdf5_ophys_params["dandiset_id"], hdf5_ophys_params["dandi_path"], follow_redirects=1
)
hdf5_ophys_params["https_url_no_redirect"] = (
    "https://api.dandiarchive.org/api/assets/c15b3e06-f443-4964-a6b0-c44c367d830b/download/"
)

hdf5_icephys_params = dict(
    dandiset_id="000717",
    dandi_path="sub-1214579789_ses-1214621812_icephys/sub-1214579789_ses-1214621812_icephys.nwb",
)
hdf5_icephys_params["https_url_redirected"] = get_https_url(
    hdf5_icephys_params["dandiset_id"], hdf5_icephys_params["dandi_path"], follow_redirects=1
)
hdf5_icephys_params["https_url_no_redirect"] = (
    "https://api.dandiarchive.org/api/assets/471ef39b-806c-4946-80b5-125b55839854/download/"
)

# The Zarr https_url_directs point directly to the S3 URL for Zarr access - copied from the DANDI asset page
zarr_ecephys_params = dict(
    dandiset_id="000719",
    dandi_path="sub-npI3_ses-20190421_behavior+ecephys_rechunk.nwb.zarr",
)
zarr_ecephys_params["https_url_direct"] = (
    "https://dandiarchive.s3.amazonaws.com/zarr/d097af6b-8fd8-4d83-b649-fc6518e95d25/"
)
zarr_ecephys_params["https_url_no_redirect"] = (
    "https://api.dandiarchive.org/api/assets/58de1d1c-278f-4278-953a-bf8790de4c69/download/"
)

zarr_ophys_params = dict(
    dandiset_id="000719",
    dandi_path="sub-R6_ses-20200206T210000_behavior+ophys_DirectoryStore_rechunked.nwb.zarr",
)
zarr_ophys_params["https_url_direct"] = (
    "https://dandiarchive.s3.amazonaws.com/zarr/c8c6b848-fbc6-4f58-85ff-e3f2618ee983/"
)
zarr_ophys_params["https_url_no_redirect"] = (
    "https://api.dandiarchive.org/api/assets/f270e686-f465-4a28-a457-4ffdcacc92b3/download/"
)

zarr_icephys_params = dict(
    dandiset_id="000719",
    dandi_path="icephys_DS_11_21_24/sub-1214579789_ses-1214621812_icephys_DirectoryStore.nwb.zarr",
)
zarr_icephys_params["https_url_direct"] = (
    "https://dandiarchive.s3.amazonaws.com/zarr/18e75d22-f527-4051-a4c8-c7e0f1e7dad1/"
)
zarr_icephys_params["https_url_no_redirect"] = (
    "https://api.dandiarchive.org/api/assets/143cf884-fe0c-4957-a45f-c3acff090f1f/download/"
)

lindi_ecephys_params = dict(
    dandiset_id="213889",
    dandi_path="sub-npI3/sub-npI3_behavior+ecephys.nwb.lindi.json",
)
lindi_ecephys_params["https_url_no_redirect"] = (
    "https://api.sandbox.dandiarchive.org/api/assets/9e9c67dc-279a-4df3-94d5-00366c164b90/download/"
)

lindi_ophys_params = dict(
    dandiset_id="213889",
    dandi_path="sub-R6/sub-R6_behavior+ophys.nwb.lindi.json",
)
lindi_ophys_params["https_url_no_redirect"] = (
    "https://api.sandbox.dandiarchive.org/api/assets/62182082-ab1d-4901-929c-2c9747efa8aa/download/"
)

lindi_icephys_params = dict(
    dandiset_id="213889",
    dandi_path="sub-1214579789_ses-1214621812_icephys/sub-1214579789_ses-1214621812_icephys.lindi.json",
)
lindi_icephys_params["https_url_no_redirect"] = (
    "https://api.sandbox.dandiarchive.org/api/assets/280cc5b5-08da-48ee-850b-7ffe599bdff5/download/"
)

################################### REMOTE FILE READ PARAMETERS ###################################
hdf5_redirected_read_params = (
    dict(
        name="EcephysTestCase",
        https_url=hdf5_ecephys_params["https_url_redirected"],
    ),
    dict(
        name="OphysTestCase",
        https_url=hdf5_ophys_params["https_url_redirected"],
    ),
    dict(
        name="IcephysTestCase",
        https_url=hdf5_icephys_params["https_url_redirected"],
    ),
)

# TODO Test non-consolidated metadata vs consolidated metadata
# These parameters point to the direct S3 URL for Zarr data access
zarr_direct_read_params = (
    dict(
        name="EcephysTestCase",
        https_url=zarr_ecephys_params["https_url_direct"],
    ),
    dict(
        name="OphysTestCase",
        https_url=zarr_ophys_params["https_url_direct"],
    ),
    dict(
        name="IcephysTestCase",
        https_url=zarr_icephys_params["https_url_direct"],
    ),
)

################################### DOWNLOAD AND LOCAL FILE READ PARAMETERS ###################################

# dandi API does not know how to handle redirected URLs, so only use no-redirect URLs for download benchmarks
# and for local file reading benchmarks that look for the already downloaded files
hdf5_no_redirect_download_params = (
    dict(
        name="EcephysTestCase",
        https_url=hdf5_ecephys_params["https_url_no_redirect"],
    ),
    dict(
        name="OphysTestCase",
        https_url=hdf5_ophys_params["https_url_no_redirect"],
    ),
    dict(
        name="IcephysTestCase",
        https_url=hdf5_icephys_params["https_url_no_redirect"],
    ),
)

# dandi API does not know how to handle redirected URLs, so only use no-redirect URLs for download benchmarks
# and for local file reading benchmarks that look for the already downloaded files
zarr_no_redirect_download_params = (
    dict(
        name="EcephysTestCase",
        https_url=zarr_ecephys_params["https_url_no_redirect"],
    ),
    dict(
        name="OphysTestCase",
        https_url=zarr_ophys_params["https_url_no_redirect"],
    ),
    dict(
        name="IcephysTestCase",
        https_url=zarr_icephys_params["https_url_no_redirect"],
    ),
)

#################################### LINDI DOWNLOAD AND FILE READ PARAMETERS ###################################

# Parameters for LINDI pointing to an existing remote LINDI reference file system JSON file
# LINDI files are only accessed in these benchmarks by downloading the entire file so there is no
# separate set of parameters for reading with redirects
lindi_no_redirect_download_params = (
    dict(
        name="EcephysTestCase",
        https_url=lindi_ecephys_params["https_url_no_redirect"],
    ),
    dict(
        name="OphysTestCase",
        https_url=lindi_ophys_params["https_url_no_redirect"],
    ),
    dict(
        name="IcephysTestCase",
        https_url=lindi_icephys_params["https_url_no_redirect"],
    ),
)

#################################### REMOTE FILE SLICE PARAMETERS ###################################
# ecephys data has shape (N, 384) and chunk shape (262144, 32)
ecephys_slices = [(slice(0, 262_144 * i), slice(0, 32)) for i in range(1, 6)]

# ophys data has shape (N, 796, 512) and chunk shape (20, 796, 512)
ophys_slices = [(slice(0, 20 * i), slice(0, 796), slice(0, 512)) for i in range(1, 6)]

# icephys data has shape (N,) and chunk shape (8192,)
icephys_slices = [(slice(0, 8192 * i),) for i in range(1, 6)]

#################################### INCREMENTAL SLICE PARAMETERS ###################################


def filter_incremental_slice_params_by_modality(params: tuple[dict, ...]) -> tuple[dict, ...]:
    """Filter incremental slicing benchmark params by RUN_INCREMENTAL_SLICING_BENCHMARKS modality selection."""
    if RUN_INCREMENTAL_SLICING_BENCHMARK_MODALITIES is None:
        return params

    return tuple(
        parameter_set
        for parameter_set in params
        if parameter_set.get("modality") in RUN_INCREMENTAL_SLICING_BENCHMARK_MODALITIES
    )


incremental_hdf5_ecephys_params = dict(
    name="EcephysIncrementalSliceTestCase",
    modality="ecephys",
    object_name="ElectricalSeries",
    slice_template=ecephys_slices[0],
    slice_strategy="iterate_time_axis",
)
incremental_hdf5_ophys_params = dict(
    name="OphysIncrementalSliceTestCase",
    modality="ophys",
    object_name="TwoPhotonSeries",
    slice_template=ophys_slices[0],
    slice_strategy="iterate_time_axis",
)
incremental_hdf5_icephys_params = dict(
    name="IcephysIncrementalSliceTestCase",
    modality="icephys",
    slice_strategy="iterate_icephys_timeseries",
)

hdf5_redirected_read_incremental_slice_params = filter_incremental_slice_params_by_modality(
    (
        dict(**incremental_hdf5_ecephys_params, https_url=hdf5_ecephys_params["https_url_redirected"]),
        dict(**incremental_hdf5_ophys_params, https_url=hdf5_ophys_params["https_url_redirected"]),
        dict(**incremental_hdf5_icephys_params, https_url=hdf5_icephys_params["https_url_redirected"]),
    )
)

hdf5_no_redirect_download_incremental_slice_params = filter_incremental_slice_params_by_modality(
    (
        dict(**incremental_hdf5_ecephys_params, https_url=hdf5_ecephys_params["https_url_no_redirect"]),
        dict(**incremental_hdf5_ophys_params, https_url=hdf5_ophys_params["https_url_no_redirect"]),
        dict(**incremental_hdf5_icephys_params, https_url=hdf5_icephys_params["https_url_no_redirect"]),
    )
)

zarr_direct_read_incremental_slice_params = filter_incremental_slice_params_by_modality(
    (
        dict(**incremental_hdf5_ecephys_params, https_url=zarr_ecephys_params["https_url_direct"]),
        dict(**incremental_hdf5_ophys_params, https_url=zarr_ophys_params["https_url_direct"]),
        dict(**incremental_hdf5_icephys_params, https_url=zarr_icephys_params["https_url_direct"]),
    )
)

zarr_no_redirect_download_incremental_slice_params = filter_incremental_slice_params_by_modality(
    (
        dict(**incremental_hdf5_ecephys_params, https_url=zarr_ecephys_params["https_url_no_redirect"]),
        dict(**incremental_hdf5_ophys_params, https_url=zarr_ophys_params["https_url_no_redirect"]),
        dict(**incremental_hdf5_icephys_params, https_url=zarr_icephys_params["https_url_no_redirect"]),
    )
)

lindi_no_redirect_download_incremental_slice_params = filter_incremental_slice_params_by_modality(
    (
        dict(**incremental_hdf5_ecephys_params, https_url=lindi_ecephys_params["https_url_no_redirect"]),
        dict(**incremental_hdf5_ophys_params, https_url=lindi_ophys_params["https_url_no_redirect"]),
        dict(**incremental_hdf5_icephys_params, https_url=lindi_icephys_params["https_url_no_redirect"]),
    )
)

#################################### REMOTE SLICE PARAMETERS ###################################

hdf5_redirected_read_slice_params = []
for index, slice_range in enumerate(ecephys_slices):
    hdf5_redirected_read_slice_params.append(
        dict(
            name=f"EcephysTestCase{index + 1}",
            https_url=hdf5_ecephys_params["https_url_redirected"],
            object_name="ElectricalSeries",
            slice_range=slice_range,
        )
    )

for index, slice_range in enumerate(ophys_slices):
    hdf5_redirected_read_slice_params.append(
        dict(
            name=f"OphysTestCase{index + 1}",
            https_url=hdf5_ophys_params["https_url_redirected"],
            object_name="TwoPhotonSeries",
            slice_range=slice_range,
        )
    )
for index, slice_range in enumerate(icephys_slices):
    hdf5_redirected_read_slice_params.append(
        dict(
            name=f"IcephysTestCase{index + 1}",
            https_url=hdf5_icephys_params["https_url_redirected"],
            object_name="data_00002_AD0",
            slice_range=slice_range,
        )
    )

zarr_direct_read_slice_params = []
for index, slice_range in enumerate(ecephys_slices):
    zarr_direct_read_slice_params.append(
        dict(
            name=f"EcephysTestCase{index + 1}",
            https_url=zarr_ecephys_params["https_url_direct"],
            object_name="ElectricalSeries",
            slice_range=slice_range,
        )
    )
for index, slice_range in enumerate(ophys_slices):
    zarr_direct_read_slice_params.append(
        dict(
            name=f"OphysTestCase{index + 1}",
            https_url=zarr_ophys_params["https_url_direct"],
            object_name="TwoPhotonSeries",
            slice_range=slice_range,
        )
    )
for index, slice_range in enumerate(icephys_slices):
    zarr_direct_read_slice_params.append(
        dict(
            name=f"IcephysTestCase{index + 1}",
            https_url=zarr_icephys_params["https_url_direct"],
            object_name="data_00002_AD0",
            slice_range=slice_range,
        )
    )

################################### LOCAL FILE SLICE PARAMETERS ###################################
hdf5_no_redirect_download_slice_params = []
for index, slice_range in enumerate(ecephys_slices):
    hdf5_no_redirect_download_slice_params.append(
        dict(
            name=f"EcephysTestCase{index + 1}",
            https_url=hdf5_ecephys_params["https_url_no_redirect"],
            object_name="ElectricalSeries",
            slice_range=slice_range,
        )
    )

for index, slice_range in enumerate(ophys_slices):
    hdf5_no_redirect_download_slice_params.append(
        dict(
            name=f"OphysTestCase{index + 1}",
            https_url=hdf5_ophys_params["https_url_no_redirect"],
            object_name="TwoPhotonSeries",
            slice_range=slice_range,
        )
    )
for index, slice_range in enumerate(icephys_slices):
    hdf5_no_redirect_download_slice_params.append(
        dict(
            name=f"IcephysTestCase{index + 1}",
            https_url=hdf5_icephys_params["https_url_no_redirect"],
            object_name="data_00002_AD0",
            slice_range=slice_range,
        )
    )

zarr_no_redirect_download_slice_params = []
for index, slice_range in enumerate(ecephys_slices):
    zarr_no_redirect_download_slice_params.append(
        dict(
            name=f"EcephysTestCase{index + 1}",
            https_url=zarr_ecephys_params["https_url_no_redirect"],
            object_name="ElectricalSeries",
            slice_range=slice_range,
        )
    )
for index, slice_range in enumerate(ophys_slices):
    zarr_no_redirect_download_slice_params.append(
        dict(
            name=f"OphysTestCase{index + 1}",
            https_url=zarr_ophys_params["https_url_no_redirect"],
            object_name="TwoPhotonSeries",
            slice_range=slice_range,
        )
    )
for index, slice_range in enumerate(icephys_slices):
    zarr_no_redirect_download_slice_params.append(
        dict(
            name=f"IcephysTestCase{index + 1}",
            https_url=zarr_icephys_params["https_url_no_redirect"],
            object_name="data_00002_AD0",
            slice_range=slice_range,
        )
    )

############################### LINDI SLICE PARAMETERS ###################################

lindi_no_redirect_download_slice_params = []
for index, slice_range in enumerate(ecephys_slices):
    lindi_no_redirect_download_slice_params.append(
        dict(
            name=f"EcephysTestCase{index + 1}",
            https_url=lindi_ecephys_params["https_url_no_redirect"],
            object_name="ElectricalSeries",
            slice_range=slice_range,
        )
    )
for index, slice_range in enumerate(ophys_slices):
    lindi_no_redirect_download_slice_params.append(
        dict(
            name=f"OphysTestCase{index + 1}",
            https_url=lindi_ophys_params["https_url_no_redirect"],
            object_name="TwoPhotonSeries",
            slice_range=slice_range,
        )
    )
for index, slice_range in enumerate(icephys_slices):
    lindi_no_redirect_download_slice_params.append(
        dict(
            name=f"IcephysTestCase{index + 1}",
            https_url=lindi_icephys_params["https_url_no_redirect"],
            object_name="data_00002_AD0",
            slice_range=slice_range,
        )
    )
