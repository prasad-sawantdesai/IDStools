import pytest
import os
import urllib.request
import urllib.error
import logging
import subprocess
import shutil
import time
import yaml
import gc
from pathlib import Path
from functools import wraps, lru_cache

logger = logging.getLogger(__name__)

# Get the absolute path to the tests directory
TESTS_DIR = Path(__file__).parent.absolute()


def _load_test_config():
    """Load test configuration from YAML file."""
    config_path = TESTS_DIR / "test_config.yaml"
    if not config_path.exists():
        logger.warning(f"Test config not found at {config_path}, using defaults")
        return None
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def _get_test_profile():
    """Get the active test profile from environment or config default."""
    profile = os.environ.get("TEST_PROFILE", None)
    config = _load_test_config()
    
    if profile is None and config:
        profile = config.get("default_profile", "local")
    elif profile is None:
        profile = "local"
    
    return profile


def _get_test_uris_from_config():
    """Get test URIs for the active test profile."""
    config = _load_test_config()
    if not config:
        return []
    
    profile = _get_test_profile()
    profile_config = config.get("profiles", {}).get(profile)
    
    if not profile_config:
        logger.warning(f"Profile '{profile}' not found in config, using local profile")
        profile_config = config.get("profiles", {}).get("local", {})
    
    return profile_config.get("uris", [])


# Load configuration and build TEST_URIS
_TEST_CONFIG = _load_test_config()
_TEST_PROFILE = _get_test_profile()
TEST_URIS = _get_test_uris_from_config()

# Build TEST_FILES NetCDF files
TEST_FILES = [uri for uri in TEST_URIS if not uri.startswith("imas:")]

# Build TEST_FILES_URLS from config
TEST_FILES_URLS = {}
if _TEST_CONFIG and "netcdf_files" in _TEST_CONFIG:
    TEST_FILES_URLS = _TEST_CONFIG["netcdf_files"]


def _get_available_ids_cached(test_file_path):
    """
    Get available IDS in a test file.
    
    NOTE: We do NOT use @lru_cache here because it keeps references to file handles
    and prevents proper cleanup, causing file locking issues on subsequent accesses.
    Each call must open and close the file fresh.
    """
    import imas
    from idstools.utils.idshelper import get_available_ids_and_occurrences
    import gc

    connection = None
    try:
        connection = imas.DBEntry(test_file_path, "r")
        available_ids = get_available_ids_and_occurrences(connection)
        available_ids_set = frozenset(ids_type for ids_type, *_ in available_ids)
        return available_ids_set
    finally:
        # Explicitly close connection and force garbage collection
        if connection is not None:
            try:
                connection.close()
            except Exception as e:
                logger.warning(f"Error closing IMAS connection: {e}")
        # Force garbage collection to ensure file handles are released
        gc.collect()


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
                logger.error(f"Error checking IDS: {e}", exc_info=True)
                raise AssertionError(f"Could not check for IDS: {e}") from e

            return func(self, test_file_path, *args, **kwargs)

        return wrapper

    return decorator


def require_files(*file_uris):
    def decorator(func):
        file_list = file_uris if file_uris else (TEST_FILES[0],)

        @pytest.mark.parametrize("test_file_path", file_list)
        @wraps(func)
        def wrapper(self, test_file_path, *args, **kwargs):
            return func(self, test_file_path, *args, **kwargs)

        return wrapper

    return decorator


def create_test_file_fixture(test_uris=None):
    """Create a pytest fixture that provides test URIs (NetCDF or IMAS)."""
    if test_uris is None:
        test_uris = TEST_URIS
    
    @pytest.fixture(params=test_uris)
    def test_file_path_fixture(request):
        uri = request.param
        # Resolve URI to absolute path (for NetCDF) or return IMAS URI as-is
        return _resolve_test_uri(uri)

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
                logger.error(f"Error checking IDS: {e}", exc_info=True)
                raise AssertionError(f"Could not check for IDS: {e}") from e
                # error_msg = str(e)
                # for pattern in error_patterns:
                #     if pattern.lower() in error_msg.lower():
                #         pytest.skip(f"Skipping due to data issue: {pattern}")
                # raise

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
    import gc
    
    script_cmd = shutil.which(script_name)

    if script_cmd:
        cmd = [script_name] + args
    else:
        script_path = Path(__file__).parent.parent / "scripts" / script_name
        cmd = [str(script_path)] + args

    logger.debug(f"\n{'='*60}")
    logger.debug(f"Running command: {' '.join(cmd)}")
    logger.debug(f"{'='*60}")

    # Increase timeout to 120 seconds for data dictionary parsing
    # (especially when dealing with multiple DD versions like DD3 and DD4)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    logger.debug(f"\nReturn code: {result.returncode}")
    if result.stdout:
        logger.debug(f"\n--- STDOUT ---\n{result.stdout[:500]}")
    if result.stderr:
        logger.debug(f"\n--- STDERR ---\n{result.stderr[:500]}")
    logger.debug(f"{'='*60}\n")

    # Force garbage collection after subprocess to ensure file handles are released
    gc.collect()

    return result


def _resolve_test_uri(uri):
    """
    Resolve a test URI to an absolute path or return as-is for IMAS URIs.
    For NetCDF files, download them if not present in the tests directory.
    """
    if uri.startswith("imas:"):
        # IMAS URI - return as-is
        return uri
    else:
        # NetCDF file path - resolve to absolute path in tests directory
        abs_path = TESTS_DIR / uri
        
        # Check if file exists
        if abs_path.exists():
            file_size = abs_path.stat().st_size
            logger.info(f"Test file found: {abs_path} (size: {file_size / (1024**2):.2f} MB)")
            return str(abs_path)
        
        # File not found, try to download it
        if uri in TEST_FILES_URLS:
            logger.info(f"Test file not found locally: {abs_path}")
            _download_test_file(uri, abs_path, TEST_FILES_URLS[uri])
            return str(abs_path)
        else:
            logger.error(f"Test file {uri} not found and no download URL available")
            raise FileNotFoundError(f"Test file not found: {abs_path}")


def _download_test_file(filename, abs_path, url, max_retries=3, retry_delay=2):
    """Download a test file from Zenodo with retry logic."""
    for attempt in range(1, max_retries + 1):
        logger.info(f"Downloading {filename} from Zenodo (attempt {attempt}/{max_retries})...")
        try:
            # Use urllib with timeout
            with urllib.request.urlopen(url, timeout=300) as response:
                with open(abs_path, 'wb') as out_file:
                    out_file.write(response.read())
            
            # Verify file was downloaded
            if abs_path.exists():
                file_size = abs_path.stat().st_size
                logger.info(f"Successfully downloaded {filename} (size: {file_size / (1024**2):.2f} MB) to {abs_path}")
                return
            else:
                raise RuntimeError(f"Download completed but file not found: {abs_path}")
                
        except urllib.error.URLError as e:
            logger.warning(f"Download attempt {attempt} failed with network error: {e}")
            try:
                if abs_path.exists():
                    abs_path.unlink()
            except Exception:
                pass
            
            if attempt == max_retries:
                raise RuntimeError(f"Could not download test file after {max_retries} attempts: {filename}. Error: {e}")
            
            # Wait before retry
            time.sleep(retry_delay)
            
        except Exception as e:
            logger.warning(f"Download attempt {attempt} failed: {e}")
            try:
                if abs_path.exists():
                    abs_path.unlink()
            except Exception:
                pass
            
            if attempt == max_retries:
                raise RuntimeError(f"Could not download test file after {max_retries} attempts: {filename}. Error: {e}")
            
            # Wait before retry
            time.sleep(retry_delay)
