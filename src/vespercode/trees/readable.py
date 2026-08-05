"""T10.2 legacy step 10.C: the minimal immutable-tree read protocol.

``ReadableTreeV1`` is the one structural surface through which every
consumer observes an immutable tree: a read-only identity digest,
deterministic canonical directory/file-path enumeration, and exact raw
byte reads.  It is deliberately the entire observation surface — there is
no mutation method, no partial/seek read, no filesystem handle, and no
path into mutable workspace state; a conforming tree can only ever be
read through these bounded methods and the immutable digest (the SPEC
§4.3 boundary: "The protocol exposes only immutable digest, canonical
directory/file-path enumeration, and exact byte reads").  Tree entry
construction, root digest computation, and integrity verification remain
in the owning module (GREEN-4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.vespercode.canonical.path_v1 import CanonicalRelativePathV1


@runtime_checkable
class ReadableTreeV1(Protocol):
    """The minimal immutable-tree read protocol.

    Every conforming tree exposes exactly this read-only surface:

    - ``digest``: one immutable identity binding the tree's sealed fields;
    - ``list_directories`` / ``list_file_paths``: deterministic canonical
      directory and file path enumeration;
    - ``read_bytes``: the exact sealed raw bytes of one tree file.

    The protocol is structural: any object with these members satisfies it,
    and ``SnapshotTreeV1`` is its sole production implementation.
    """

    @property
    def digest(self) -> str:
        """One immutable digest binding every sealed tree field."""

    def list_directories(self) -> tuple[CanonicalRelativePathV1, ...]:
        """Every directory under the tree root, in canonical path order."""

    def list_file_paths(self) -> tuple[CanonicalRelativePathV1, ...]:
        """Every file path in the tree, in canonical path order."""

    def read_bytes(self, path: CanonicalRelativePathV1) -> bytes:
        """The exact sealed raw bytes of one tree file.

        Raises ``KeyError`` when ``path`` is not a file path of this tree.
        """
