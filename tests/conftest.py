"""Pytest configuration for idstools tests."""

import pytest


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
