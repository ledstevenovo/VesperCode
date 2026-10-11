"""VesperCode coding agent harness package identity.

The released v1 package remains ``0.1.0`` in the historical release record.
The current source line is the relaxed-identity v2 alpha and uses a fresh
database path; v1 records are not silently upgraded or reused.
"""

LEGACY_VERSION = "0.1.0"
V2_VERSION = "0.2.0a0"
__version__ = V2_VERSION

__all__ = ("LEGACY_VERSION", "V2_VERSION", "__version__")
