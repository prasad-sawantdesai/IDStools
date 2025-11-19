"""Pytest configuration for idstools tests."""

import pytest


def _print_library_versions():
    """Print versions of key libraries used in tests."""
    try:
        import numpy
        numpy_version = numpy.__version__
    except ImportError:
        numpy_version = "Not installed"
    
    try:
        import h5py
        h5py_version = h5py.__version__
        h5_version = h5py.version.hdf5_version
    except ImportError:
        h5py_version = "Not installed"
        h5_version = "Not installed"
    
    try:
        import netCDF4
        netcdf_version = netCDF4.__version__
    except ImportError:
        netcdf_version = "Not installed"
    
    try:
        import imas
        imas_version = imas.__version__
    except (ImportError, AttributeError):
        imas_version = "Not installed"
    
    version_info = f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    Test Environment Versions                         ║
╠══════════════════════════════════════════════════════════════════════╣
║  NumPy:              {numpy_version:<47} ║
║  h5py:               {h5py_version:<47} ║
║  HDF5:               {h5_version:<47} ║
║  NetCDF4:            {netcdf_version:<47} ║
║  IMAS:               {imas_version:<47} ║
╚══════════════════════════════════════════════════════════════════════╝
"""
    print(version_info)


def pytest_addoption(parser):
    """Add command line option to specify test file or URI."""
    parser.addoption(
        "--test-file",
        action="store",
        default=None,
        help="Override test file/URI to use for all tests (e.g., 'file.nc' or 'imas:hdf5?...')",
    )


def pytest_configure(config):
    """Configure pytest with custom markers and handle --test-file option."""
    # Print library versions at test start
    _print_library_versions()
    
    # Store test file option globally if provided
    test_file = config.getoption("--test-file")
    if test_file:
        config._test_file_override = test_file


def pytest_generate_tests(metafunc):
    """Override parametrization if --test-file is provided."""
    if hasattr(metafunc.config, "_test_file_override"):
        test_file = metafunc.config._test_file_override
        if "test_file_path" in metafunc.fixturenames:
            # Remove any existing parametrization markers
            for marker in list(metafunc.definition.own_markers):
                if marker.name == "parametrize":
                    # Check if this parametrize is for test_file_path
                    if marker.args and marker.args[0] == "test_file_path":
                        # Remove this marker to avoid conflict
                        metafunc.definition.own_markers.remove(marker)

            # Check if test_file_path is a parametrized fixture
            # If so, we need to override the fixture's params
            if "test_file_path" in metafunc.fixturenames:
                # Get the fixture definition
                fixtureinfo = metafunc._arg2fixturedefs.get("test_file_path")
                if fixtureinfo:
                    # Override the fixture's params if it's parametrized
                    for fixturedef in fixtureinfo:
                        if hasattr(fixturedef, "params"):
                            # Replace params with our override
                            fixturedef.params = [test_file]
                            return

            # If no parametrized fixture found, apply direct parametrization
            metafunc.parametrize("test_file_path", [test_file])


@pytest.fixture(autouse=True)
def cleanup_file_handles():
    """
    Automatically cleanup file handles after each test.
    """
    yield
    
    # Give subprocesses time to exit and release file handles
    import time
    import gc
    time.sleep(0.5)
    gc.collect()
