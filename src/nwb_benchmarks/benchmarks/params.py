from concurrent.futures import ThreadPoolExecutor

from nwb_benchmarks.core import get_https_url

################################### BASE PARAMETERS ###################################
hdf5_ecephys_params = dict(
    dandiset_id="000717",
    dandi_path="sub-npI3/sub-npI3_behavior+ecephys.nwb",
)

hdf5_ophys_params = dict(
    dandiset_id="000717",
    dandi_path="sub-R6/sub-R6_behavior+ophys.nwb",
)

hdf5_icephys_params = dict(
    dandiset_id="000717",
    dandi_path="sub-1214579789_ses-1214621812_icephys/sub-1214579789_ses-1214621812_icephys.nwb",
)

# The Zarr https_url_directs point directly to the S3 URL for Zarr access - copied from the DANDI asset page
zarr_ecephys_params = dict(
    dandiset_id="000719",
    dandi_path="sub-npI3_ses-20190421_behavior+ecephys_rechunk.nwb.zarr",
)
zarr_ecephys_params["https_url_direct"] = (
    "https://dandiarchive.s3.amazonaws.com/zarr/d097af6b-8fd8-4d83-b649-fc6518e95d25/"
)

zarr_ophys_params = dict(
    dandiset_id="000719",
    dandi_path="sub-R6_ses-20200206T210000_behavior+ophys_DirectoryStore_rechunked.nwb.zarr",
)
zarr_ophys_params["https_url_direct"] = (
    "https://dandiarchive.s3.amazonaws.com/zarr/c8c6b848-fbc6-4f58-85ff-e3f2618ee983/"
)

zarr_icephys_params = dict(
    dandiset_id="000719",
    dandi_path="icephys_DS_11_21_24/sub-1214579789_ses-1214621812_icephys_DirectoryStore.nwb.zarr",
)
zarr_icephys_params["https_url_direct"] = (
    "https://dandiarchive.s3.amazonaws.com/zarr/18e75d22-f527-4051-a4c8-c7e0f1e7dad1/"
)

lindi_ecephys_params = dict(
    dandiset_id="213889",
    dandi_path="sub-npI3/sub-npI3_behavior+ecephys.nwb.lindi.json",
)

lindi_ophys_params = dict(
    dandiset_id="213889",
    dandi_path="sub-R6/sub-R6_behavior+ophys.nwb.lindi.json",
)

lindi_icephys_params = dict(
    dandiset_id="213889",
    dandi_path="sub-1214579789_ses-1214621812_icephys/sub-1214579789_ses-1214621812_icephys.lindi.json",
)


def _resolve_https_urls(params: dict, redirected: bool) -> None:
    """Add the download URL(s) of the asset described by `params`, resolved through the DANDI API."""
    if redirected:
        params["https_url_redirected"] = get_https_url(params["dandiset_id"], params["dandi_path"], follow_redirects=1)
    params["https_url_no_redirect"] = get_https_url(params["dandiset_id"], params["dandi_path"], follow_redirects=False)


# Resolving each URL takes several DANDI API requests, and ASV imports this module in every process it starts
# (benchmark discovery and the benchmark fork server), so resolve all assets concurrently instead of one by one
_assets_to_resolve = [
    (hdf5_ecephys_params, True),
    (hdf5_ophys_params, True),
    (hdf5_icephys_params, True),
    (zarr_ecephys_params, False),
    (zarr_ophys_params, False),
    (zarr_icephys_params, False),
    (lindi_ecephys_params, False),
    (lindi_ophys_params, False),
    (lindi_icephys_params, False),
]
with ThreadPoolExecutor(max_workers=len(_assets_to_resolve)) as _executor:
    _futures = [_executor.submit(_resolve_https_urls, params, redirected) for params, redirected in _assets_to_resolve]
    for _future in _futures:
        _future.result()  # Re-raise any failure so a bad lookup still stops the import

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
