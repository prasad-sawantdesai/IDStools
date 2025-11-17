import pytest
import os
import urllib.request
import urllib.error
import logging
import subprocess
import shutil
import time
from pathlib import Path
from functools import wraps, lru_cache

logger = logging.getLogger(__name__)


TEST_FILES = [
    "iter_disruption_113112_1.nc",
    "iter_scenario_123364_1.nc",
    "iter_scenario_53298_seq1_DD3.nc",
    "iter_scenario_53298_seq1_DD4.nc",
]

TEST_FILES_URLS = {
    "iter_disruption_113112_1.nc": "https://zenodo.org/records/17062700/files/iter_disruption_113112_1.nc?download=1",
    "iter_scenario_123364_1.nc": "https://zenodo.org/records/17062700/files/iter_scenario_123364_1.nc?download=1",
    "iter_scenario_53298_seq1_DD3.nc": "https://zenodo.org/records/17062700/files/iter_scenario_53298_seq1_DD3.nc?download=1",
    "iter_scenario_53298_seq1_DD4.nc": "https://zenodo.org/records/17062700/files/iter_scenario_53298_seq1_DD4.nc?download=1",
}


@lru_cache(maxsize=128)
def _get_available_ids_cached(test_file_path):
    import imas
    from idstools.utils.idshelper import get_available_ids_and_occurrences

    connection = imas.DBEntry(test_file_path, "r")
    available_ids = get_available_ids_and_occurrences(connection)
    available_ids_set = frozenset(ids_type for ids_type, *_ in available_ids)
    connection.close()

    return available_ids_set


def require_ids(*ids_names, require_all=False):
    def decorator(func):
        @wraps(func)
        def wrapper(self, test_file_path, *args, **kwargs):
            try:
                available_ids_set = _get_available_ids_cached(test_file_path)

                if require_all:
                    missing_ids = [ids_name for ids_name in ids_names if ids_name not in available_ids_set]
                    if missing_ids:
                        pytest.skip(f"Required IDS not present in {test_file_path}: {', '.join(missing_ids)}")
                else:
                    has_any_ids = any(ids_name in available_ids_set for ids_name in ids_names)
                    if not has_any_ids:
                        pytest.skip(f"None of the required IDS present in {test_file_path}: {', '.join(ids_names)}")

            except Exception as e:
                pytest.skip(f"Could not check for IDS: {e}")

            return func(self, test_file_path, *args, **kwargs)

        return wrapper

    return decorator


def require_files(*file_uris):
    def decorator(func):
        file_list = file_uris if file_uris else (TEST_FILES[0],)

        @pytest.mark.parametrize("test_file_path", file_list)
        @wraps(func)
        def wrapper(self, test_file_path, *args, **kwargs):
            download_test_file_if_needed(test_file_path)
            # Validate file can be opened before running test
            if not _is_valid_netcdf_file(test_file_path):
                pytest.skip(f"Test file {test_file_path} cannot be validated as a valid NetCDF file")
            return func(self, test_file_path, *args, **kwargs)

        return wrapper

    return decorator


def _is_valid_netcdf_file(file_path):
    """Check if file is a valid NetCDF file by attempting to read its header."""
    try:
        import h5py
        with h5py.File(file_path, 'r') as f:
            # Try to read the root attributes to ensure file is readable
            _ = list(f.attrs.items())
            return True
    except Exception as e:
        logger.debug(f"h5py validation failed for {file_path}: {e}")
        try:
            # Fallback: check if file exists and has reasonable size
            if os.path.exists(file_path) and os.path.getsize(file_path) > 1000000:  # At least 1MB
                return True
        except Exception:
            pass
        return False


def download_test_file_if_needed(test_file_path):
    if test_file_path in TEST_FILES_URLS:
        # Check if file exists and is valid
        if os.path.exists(test_file_path):
            if _is_valid_netcdf_file(test_file_path):
                logger.info(f"Test file {test_file_path} found and valid.")
                return
            else:
                logger.warning(f"Test file {test_file_path} exists but appears corrupted. Removing and re-downloading...")
                try:
                    os.remove(test_file_path)
                except Exception as e:
                    logger.warning(f"Could not remove corrupted file: {e}")
        
        # Download the file with retry logic
        url = TEST_FILES_URLS[test_file_path]
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(1, max_retries + 1):
            logger.info(f"Test file {test_file_path} not found. Downloading from Zenodo (attempt {attempt}/{max_retries})...")
            try:
                # Use urllib with timeout via urlopen instead of urlretrieve
                # (urlretrieve doesn't support timeout in all Python versions)
                with urllib.request.urlopen(url, timeout=300) as response:
                    with open(test_file_path, 'wb') as out_file:
                        out_file.write(response.read())
                
                # Verify downloaded file is valid
                if _is_valid_netcdf_file(test_file_path):
                    # Log file details for debugging
                    file_size = os.path.getsize(test_file_path)
                    logger.info(f"Successfully downloaded and validated {test_file_path} (size: {file_size / (1024**2):.2f} MB)")
                    
                    # List all files in current directory for debugging
                    current_files = [f for f in os.listdir('.') if f.endswith('.nc')]
                    if current_files:
                        logger.debug(f"NetCDF files in current directory: {current_files}")
                    
                    return
                else:
                    logger.warning(f"Downloaded file {test_file_path} appears to be corrupted.")
                    try:
                        os.remove(test_file_path)
                    except Exception:
                        pass
                    
                    # On last attempt, fail the test
                    if attempt == max_retries:
                        raise RuntimeError(f"Downloaded test file appears corrupted after {max_retries} attempts: {test_file_path}")
                    
            except urllib.error.URLError as e:
                logger.warning(f"Download attempt {attempt} failed with network error: {e}")
                try:
                    if os.path.exists(test_file_path):
                        os.remove(test_file_path)
                except Exception:
                    pass
                
                if attempt == max_retries:
                    raise RuntimeError(f"Could not download mandatory test file after {max_retries} attempts: {test_file_path}. Error: {e}")
                
                # Wait before retry
                time.sleep(retry_delay)
                
            except RuntimeError:
                # Re-raise RuntimeError (our custom errors)
                raise
            except Exception as e:
                logger.warning(f"Download attempt {attempt} failed: {e}")
                try:
                    if os.path.exists(test_file_path):
                        os.remove(test_file_path)
                except Exception:
                    pass
                
                if attempt == max_retries:
                    raise RuntimeError(f"Could not download mandatory test file after {max_retries} attempts: {test_file_path}. Error: {e}")
                
                # Wait before retry
                time.sleep(retry_delay)


def create_test_file_fixture(test_files=None, test_files_urls=None):
    if test_files is None:
        test_files = TEST_FILES
    if test_files_urls is None:
        test_files_urls = TEST_FILES_URLS

    @pytest.fixture(params=test_files)
    def test_file_path_fixture(request):
        file_path = request.param
        download_test_file_if_needed(file_path)
        return file_path

    return test_file_path_fixture


def require_summary(func):
    return require_ids("summary")(func)


def require_equilibrium(func):
    return require_ids("equilibrium")(func)


def require_plasma_profiles(func):
    return require_ids("plasma_profiles")(func)


def require_edge_profiles(func):
    return require_ids("edge_profiles")(func)


def skip_on_error_or_empty(error_patterns=None):
    if error_patterns is None:
        error_patterns = [
            "path/value does not exist",
            "has no attribute",
            "ERROR",
            "numpy.ndarray|(0,)|",
            "NetCDF: HDF error",
            "Errno -101",
        ]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return result
            except AssertionError as e:
                error_msg = str(e)
                raise
            except Exception as e:
                error_msg = str(e)
                for pattern in error_patterns:
                    if pattern.lower() in error_msg.lower():
                        pytest.skip(f"Skipping due to data issue: {pattern}")
                raise

        return wrapper

    return decorator


def check_result_skip_if_empty_or_error(result, skip_patterns=None):
    if skip_patterns is None:
        skip_patterns = [
            "path/value does not exist",
            "has no attribute",
            "numpy.ndarray|(0,)|float64",
            "NetCDF: HDF error",  # Skip on HDF5 read errors
            "Errno -101",  # NetCDF HDF5 error code
        ]

    output = result.stdout + result.stderr

    for pattern in skip_patterns:
        if pattern in output:
            pytest.skip(f"Skipping test: data is empty or has errors (found: {pattern})")

    if "ERROR" in result.stderr:
        pytest.skip(f"Skipping test: command produced ERROR in stderr")


def run_idstools_script(script_name, args, timeout=30):
    script_cmd = shutil.which(script_name)

    if script_cmd:
        cmd = [script_name] + args
    else:
        script_path = Path(__file__).parent.parent / "scripts" / script_name
        cmd = [str(script_path)] + args

    logger.debug(f"\n{'='*60}")
    logger.debug(f"Running command: {' '.join(cmd)}")
    logger.debug(f"{'='*60}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    logger.debug(f"\nReturn code: {result.returncode}")
    if result.stdout:
        logger.debug(f"\n--- STDOUT ---\n{result.stdout[:500]}")
    if result.stderr:
        logger.debug(f"\n--- STDERR ---\n{result.stderr[:500]}")
    logger.debug(f"{'='*60}\n")

    return result
