import ctypes.util

import pytest

from mpcasu_backend import LibVLCBackend


class _HeadlessSurface:
    def winfo_id(self):
        return 0


@pytest.mark.media
@pytest.mark.skipif(not ctypes.util.find_library("vlc"), reason="libVLC unavailable")
def test_installed_libvlc_runtime_initializes_and_reports_version():
    backend = LibVLCBackend(_HeadlessSurface())
    try:
        capabilities = backend.capabilities()
        assert capabilities["backend"] == "libVLC shared library"
        assert capabilities["version"] != "unknown"
        assert capabilities["player_process"] == "none"
        # Capability is decided by libVLC at open time, never by extension.
        assert backend.supports("movie.codec-not-known-to-mpcasu")
    finally:
        backend.close()
