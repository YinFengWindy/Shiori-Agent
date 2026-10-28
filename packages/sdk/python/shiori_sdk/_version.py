"""SDK semver. A new major is a breaking change (D22).

The npm package, the host pin and host-testing use this same number.
``scripts/check_sdk_release.mjs --align`` checks they match. There is no
runtime_api version and no Unreleased batch.
"""

__version__ = "4.0.0"
