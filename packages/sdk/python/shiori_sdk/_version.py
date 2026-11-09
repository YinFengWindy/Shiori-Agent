"""SDK A.B.C: generation, compatibility line, compatible update.

B may change APIs incompatibly; C preserves the A.B contract. This custom
compatibility policy does not change numeric version ordering or range syntax.
The npm package, host and host-testing pins use this same version. See
``docs/decisions/2026-11-05-sdk-version-policy.md``.
"""

__version__ = "4.1.2"
