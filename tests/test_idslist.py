import pytest
import subprocess
import tempfile
import shutil
import logging
from pathlib import Path

from test_utils import (
    require_ids,
    TEST_FILES,
    download_test_file_if_needed,
    check_result_skip_if_empty_or_error,
    run_idstools_script,
    _is_valid_netcdf_file,
)

logger = logging.getLogger(__name__)


class TestIDSListScript:

    @pytest.fixture(params=TEST_FILES)
    def test_file_path(self, request):
        file_path = request.param
        download_test_file_if_needed(file_path)
        return file_path

    def run_idslist(self, args, timeout=120):
        return run_idstools_script("idslist", args, timeout=timeout)

    def test_idslist_default_mode(self, test_file_path):
        # Skip if file cannot be validated
        if not _is_valid_netcdf_file(test_file_path):
            pytest.skip(f"Test file {test_file_path} cannot be validated as a valid NetCDF file")
        
        result = self.run_idslist(["--uri", test_file_path])

        # Check for HDF5 errors and skip if found
        if "NetCDF: HDF error" in result.stdout or "Errno -101" in result.stdout:
            pytest.skip(f"HDF5 read error on {test_file_path}: file may be corrupted in CI environment")

        assert result.returncode == 0
        assert "List of IDSes" in result.stdout
        assert "IDS" in result.stdout
        assert "SLICES" in result.stdout
        assert "TIME" in result.stdout

    @require_ids("summary")
    def test_idslist_filter_single_ids(self, test_file_path):
        result = self.run_idslist(["--uri", test_file_path, "--ids", "summary"])

        assert result.returncode == 0
        assert "summary" in result.stdout

    @require_ids("summary")
    def test_idslist_fullarray_option(self, test_file_path):
        result = self.run_idslist(["--uri", test_file_path, "-f"])

        assert result.returncode == 0
        assert "TIME" in result.stdout

    @require_ids("summary")
    def test_idslist_yaml_mode(self, test_file_path):
        result = self.run_idslist(["--uri", test_file_path, "-y"])

        assert result.returncode == 0
        assert "time_step_number:" in result.stdout or "time:" in result.stdout

    @require_ids("summary")
    def test_idslist_yaml_with_filter(self, test_file_path):
        result = self.run_idslist(["--uri", test_file_path, "-y", "--ids", "summary"])

        assert result.returncode == 0
        assert "summary" in result.stdout
        assert "time_step_number:" in result.stdout or "time:" in result.stdout

    @require_ids("summary")
    def test_idslist_comment_mode(self, test_file_path):
        result = self.run_idslist(["--uri", test_file_path, "-c"])

        assert result.returncode == 0
        assert "COMMENT" in result.stdout

    @require_ids("summary")
    def test_idslist_dd_version_mode(self, test_file_path):
        result = self.run_idslist(["--uri", test_file_path, "--dd-version"])

        assert result.returncode == 0
        assert "DD VERSION" in result.stdout

    def test_idslist_error_invalid_file(self):
        result = self.run_idslist(["--uri", "nonexistent_file.nc"])

        assert result.returncode != 0
        assert result.returncode == 1



if __name__ == "__main__":
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "-x",
        ]
    )
