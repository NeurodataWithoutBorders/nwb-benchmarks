"""
Check that the DANDI URLs hardcoded in `nwb_benchmarks.benchmarks.params` still match what the DANDI API resolves.

Run with `python -m nwb_benchmarks.scripts.check_dandi_urls`. Exits with status 1 and prints the current values if any
URL has changed, for example because an asset was replaced on DANDI.
"""

import sys

from nwb_benchmarks.benchmarks import params
from nwb_benchmarks.core import get_https_url

# How each hardcoded key was resolved: the `follow_redirects` argument passed to `get_https_url`
FOLLOW_REDIRECTS_BY_KEY = {"https_url_redirected": 1, "https_url_no_redirect": False}


def main() -> int:
    asset_params = [
        value
        for name, value in vars(params).items()
        if name.endswith("_params") and isinstance(value, dict) and {"dandiset_id", "dandi_path"} <= set(value)
    ]

    mismatches = []
    for asset in asset_params:
        for key, follow_redirects in FOLLOW_REDIRECTS_BY_KEY.items():
            if key not in asset:
                continue
            resolved = get_https_url(asset["dandiset_id"], asset["dandi_path"], follow_redirects=follow_redirects)
            status = "ok" if resolved == asset[key] else "CHANGED"
            print(f"{status:8s} {asset['dandiset_id']} {asset['dandi_path']} {key}")
            if resolved != asset[key]:
                mismatches.append((asset, key, resolved))

    if mismatches:
        print("\nThe following URLs in nwb_benchmarks/benchmarks/params.py no longer match the DANDI API:")
        for asset, key, resolved in mismatches:
            print(f"\n  {asset['dandiset_id']} {asset['dandi_path']} {key}")
            print(f"    hardcoded: {asset[key]}")
            print(f"    resolved:  {resolved}")
        return 1

    print(
        f"\nAll {sum(len([k for k in a if k in FOLLOW_REDIRECTS_BY_KEY]) for a in asset_params)} hardcoded URLs match."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
