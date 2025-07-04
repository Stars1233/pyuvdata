# Copyright (c) 2019 Radio Astronomy Software Group
# Licensed under the 2-clause BSD License

import copy
import os
import pathlib
import re
import shutil
import warnings

import h5py
import numpy as np
import pytest
from _pytest.outcomes import Skipped
from astropy import units

from pyuvdata import UVCal, UVData, UVFlag, __version__, utils
from pyuvdata.data import DATA_PATH
from pyuvdata.testing import check_warnings
from pyuvdata.utils.io import hdf5 as hdf5_utils
from pyuvdata.uvflag import and_rows_cols, flags2waterfall

from ..utils.test_coordinates import frame_selenoid

test_d_file = os.path.join(DATA_PATH, "zen.2457698.40355.xx.HH.uvcAA")
test_c_file = os.path.join(DATA_PATH, "zen.2457555.42443.HH.uvcA.omni.calfits")
test_f_file = test_d_file + ".testuvflag.h5"

pyuvdata_version_str = "  Read/written with pyuvdata version: " + __version__ + "."

pytestmark = pytest.mark.filterwarnings(
    "ignore:telescope_location is not set. Using known values for HERA.",
    "ignore:The uvw_array does not match the expected values",
    "ignore:Fixing auto-correlations to be be real-only",
)


@pytest.fixture(scope="session")
def uvdata_obj_main():
    pytest.importorskip("pyuvdata.uvdata._miriad", exc_type=ImportError)
    uvdata_object = UVData()
    with check_warnings(
        UserWarning,
        match=[
            "Fixing auto-correlations to be be real-only",
            "The uvw_array does not match the expected",
        ],
    ):
        uvdata_object.read(test_d_file)

    yield uvdata_object

    # cleanup
    del uvdata_object

    return


@pytest.fixture(scope="function")
def uvdata_obj_weird_telparams(uvdata_obj_main):
    uvdata_object = uvdata_obj_main.copy()

    yield uvdata_object

    # cleanup
    del uvdata_object

    return


@pytest.fixture(scope="function")
def uvdata_obj(uvdata_obj_main):
    uvdata_object = uvdata_obj_main.copy()

    # This data file has a different telescope location and other weirdness.
    # Set them to the known HERA values to allow combinations with the test_f_file
    # which appears to have the known HERA values.
    uvdata_object.set_telescope_params(overwrite=True, warn=False)
    uvdata_object.set_lsts_from_time_array()

    yield uvdata_object

    # cleanup
    del uvdata_object

    return


@pytest.fixture(scope="session")
def uvcal_obj_main():
    uvc = UVCal()
    uvc.read_calfits(test_c_file)

    yield uvc

    # cleanup
    del uvc

    return


@pytest.fixture(scope="function")
def uvcal_obj(uvcal_obj_main):
    uvc = uvcal_obj_main.copy()

    # This cal file has a different antenna names and other weirdness.
    # Set them to the known HERA values to allow combinations with the test_f_file
    # which appears to have the known HERA values.
    uvc.set_telescope_params(overwrite=True, warn=False)
    yield uvc


# The following three fixtures are used regularly
# to initizize UVFlag objects from standard files
# We need to define these here in order to set up
# some skips for developers who do not have `pytest-cases` installed
@pytest.fixture(scope="function")
def uvf_from_data(uvdata_obj):
    uvf = UVFlag()
    uvf.from_uvdata(uvdata_obj)

    # yield the object for the test
    yield uvf

    # do some cleanup
    del (uvf, uvdata_obj)


@pytest.fixture(scope="function")
def uvf_from_uvcal(uvcal_obj):
    uvf = UVFlag()
    uvf.from_uvcal(uvcal_obj)

    # the antenna type test file is large, so downselect to speed up
    if uvf.type == "antenna":
        uvf.select(antenna_nums=uvf.ant_array[:5])

    # yield the object for the test
    yield uvf

    # do some cleanup
    del (uvf, uvcal_obj)


@pytest.fixture(scope="function")
def uvf_from_file_main():
    with check_warnings(
        [UserWarning] * 4 + [DeprecationWarning] * 5,
        match=["channel_width not available in file, computing it from the freq_array"],
    ):
        uvf = UVFlag(test_f_file, telescope_name="HERA")
    uvf.telescope.name = "HERA"
    uvf.telescope.antenna_numbers = None
    uvf.telescope.antenna_names = None
    uvf.set_telescope_params()

    yield uvf


@pytest.fixture(scope="function")
def uvf_from_file(uvf_from_file_main):
    yield uvf_from_file_main.copy()


@pytest.fixture(scope="function")
def uvf_from_waterfall(uvdata_obj):
    uvf = UVFlag()
    uvf.from_uvdata(uvdata_obj, waterfall=True)

    # yield the object for the test
    yield uvf

    # do some cleanup
    del uvf


# Try to import `pytest-cases` and define decorators used to
# iterate over the three main types of UVFlag objects
# otherwise make the decorators skip the tests that use these iterators
try:
    pytest_cases = pytest.importorskip("pytest_cases", minversion="1.12.1")

    cases_decorator = pytest_cases.parametrize(
        "input_uvf",
        [
            pytest_cases.fixture_ref(uvf_from_data),
            pytest_cases.fixture_ref(uvf_from_uvcal),
            pytest_cases.fixture_ref(uvf_from_waterfall),
        ],
    )

    cases_decorator_no_waterfall = pytest_cases.parametrize(
        "input_uvf",
        [
            pytest_cases.fixture_ref(uvf_from_data),
            pytest_cases.fixture_ref(uvf_from_uvcal),
        ],
    )

    # This warning is raised by pytest_cases
    # It is due to a feature the developer does
    # not know how to handle yet. ignore for now.
    warnings.filterwarnings(
        "ignore",
        message="WARNING the new order is not" + " taken into account !!",
        append=True,
    )

except Skipped:
    cases_decorator = pytest.mark.skipif(
        True, reason="pytest-cases not installed or not required version"
    )
    cases_decorator_no_waterfall = pytest.mark.skipif(
        True, reason="pytest-cases not installed or not required version"
    )


@pytest.fixture()
def test_outfile(tmp_path):
    yield str(tmp_path / "outtest_uvflag.h5")


@pytest.mark.filterwarnings("ignore:Fixing auto-correlations to be be real-only,")
@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_check_flag_array(uvdata_obj):
    uvf = UVFlag()
    uvf.from_uvdata(uvdata_obj, mode="flag")

    uvf.flag_array = np.ones((uvf.flag_array.shape), dtype=int)

    with pytest.raises(
        ValueError, match="UVParameter _flag_array is not the appropriate type."
    ):
        uvf.check()


@pytest.mark.parametrize(
    ["param", "msg"],
    [
        ("Nants_data", "Nants_data must be equal to the number of unique values in"),
        ("Nbls", "Nbls must be equal to the number of unique baselines in the"),
        ("Ntimes", "Ntimes must be equal to the number of unique times in the"),
    ],
)
def test_check_implicit_sizes(uvf_from_data, param, msg):
    uvf = uvf_from_data

    setattr(uvf, param, getattr(uvf, param) - 1)

    with pytest.raises(ValueError, match=msg):
        uvf.check()


@pytest.mark.parametrize("param", ["ant_1_array", "ant_2_array", "ant_array"])
def test_check_ant_arrays_in_ant_nums(uvf_from_data, uvf_from_uvcal, param):
    if param == "ant_array":
        uvf = uvf_from_uvcal
    else:
        uvf = uvf_from_data

    ant_array = getattr(uvf, param)
    ant_array[np.nonzero(ant_array == np.max(ant_array))] += 400
    setattr(uvf, param, ant_array)
    if param != "ant_array":
        uvf.Nants_data += 1

    with pytest.raises(
        ValueError, match=f"All antennas in {param} must be in antenna_numbers."
    ):
        uvf.check()


def test_check_flex_spw_id_array(uvf_from_data):
    uvf = uvf_from_data
    uvf.spw_array = np.arange(3)
    uvf.Nspws = 3
    uvf.flex_spw_id_array = None

    with pytest.raises(
        ValueError, match="Required UVParameter _flex_spw_id_array has not been set."
    ):
        uvf.check()

    uvf.flex_spw_id_array = np.full(uvf.Nfreqs, 5, dtype="int")
    with pytest.raises(
        ValueError,
        match="All values in the flex_spw_id_array must exist in the spw_array.",
    ):
        uvf.check()


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.filterwarnings("ignore:telescope_location, antenna_positions")
def test_init_bad_mode(uvdata_obj, uvcal_obj):
    uv = uvdata_obj
    with pytest.raises(ValueError, match="Input mode must be within acceptable"):
        UVFlag(uv, mode="bad_mode", history="I made a UVFlag object", label="test")

    uv = uvcal_obj
    with pytest.raises(ValueError, match="Input mode must be within acceptable"):
        UVFlag(uv, mode="bad_mode", history="I made a UVFlag object", label="test")


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_init_uvdata(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv, history="I made a UVFlag object", label="test")
    assert uvf.metric_array.shape == uv.flag_array.shape
    assert np.all(uvf.metric_array == 0)
    assert uvf.weights_array.shape == uv.flag_array.shape
    assert np.all(uvf.weights_array == 1)
    assert uvf.type == "baseline"
    assert uvf.mode == "metric"
    assert np.all(uvf.time_array == uv.time_array)
    assert np.all(uvf.lst_array == uv.lst_array)
    assert np.all(uvf.freq_array == uv.freq_array)
    assert np.all(uvf.polarization_array == uv.polarization_array)
    assert np.all(uvf.baseline_array == uv.baseline_array)
    assert np.all(uvf.ant_1_array == uv.ant_1_array)
    assert np.all(uvf.ant_2_array == uv.ant_2_array)
    assert "I made a UVFlag object" in uvf.history
    assert 'Flag object with type "baseline"' in uvf.history
    assert pyuvdata_version_str in uvf.history
    assert uvf.label == "test"
    assert uvf.filename == uv.filename


def test_add_extra_keywords(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv, history="I made a UVFlag object", label="test")
    uvf.extra_keywords = {"keyword1": 1, "keyword2": 2}
    assert "keyword1" in uvf.extra_keywords
    assert "keyword2" in uvf.extra_keywords
    uvf.extra_keywords["keyword3"] = 3
    assert "keyword3" in uvf.extra_keywords
    assert uvf.extra_keywords.get("keyword1") == 1
    assert uvf.extra_keywords.get("keyword2") == 2
    assert uvf.extra_keywords.get("keyword3") == 3


def test_read_extra_keywords(uvdata_obj):
    uv = uvdata_obj
    uv.extra_keywords = {"keyword1": 1, "keyword2": 2}
    assert "keyword1" in uv.extra_keywords
    assert "keyword2" in uv.extra_keywords
    uvf = UVFlag(uv, history="I made a UVFlag object", label="test")
    assert "keyword1" in uvf.extra_keywords
    assert "keyword2" in uvf.extra_keywords


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_init_uvdata_x_orientation(uvdata_obj):
    uv = uvdata_obj
    uv.telescope.set_feeds_from_x_orientation(
        "east", polarization_array=uv.polarization_array
    )
    uvf = UVFlag(uv, history="I made a UVFlag object", label="test")
    assert uvf.telescope.get_x_orientation_from_feeds() == (
        uv.telescope.get_x_orientation_from_feeds()
    )


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.filterwarnings("ignore:Fixing auto-correlations to be be real-only,")
def test_init_uvdata_copy_flags(uvdata_obj):
    uv = uvdata_obj

    warn_type = [UserWarning]
    warn_msg = ['Copying flags to type=="baseline"']

    with check_warnings(warn_type, match=warn_msg):
        uvf = UVFlag(uv, copy_flags=True, mode="metric")

    #  with copy flags uvf.metric_array should be none
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None
    assert np.array_equal(uvf.flag_array, uv.flag_array)
    assert uvf.weights_array is None
    assert uvf.type == "baseline"
    assert uvf.mode == "flag"
    assert np.all(uvf.time_array == uv.time_array)
    assert np.all(uvf.lst_array == uv.lst_array)
    assert np.all(uvf.freq_array == uv.freq_array)
    assert np.all(uvf.polarization_array == uv.polarization_array)
    assert np.all(uvf.baseline_array == uv.baseline_array)
    assert np.all(uvf.ant_1_array == uv.ant_1_array)
    assert np.all(uvf.ant_2_array == uv.ant_2_array)
    assert 'Flag object with type "baseline"' in uvf.history
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_init_uvdata_mode_flag(uvdata_obj):
    uv = uvdata_obj

    # add spectral windows to test handling
    uv.Nspws = 2
    uv.spw_array = np.array([0, 1])
    uv.flex_spw_id_array = np.zeros(uv.Nfreqs, dtype=int)
    uv.flex_spw_id_array[: uv.Nfreqs // 2] = 1
    uv.check()

    uvf = UVFlag()
    uvf.from_uvdata(uv, copy_flags=False, mode="flag")
    #  with copy flags uvf.metric_array should be none
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None
    assert np.array_equal(uvf.flag_array, uv.flag_array)
    assert uvf.weights_array is None
    assert uvf.type == "baseline"
    assert uvf.mode == "flag"
    assert np.all(uvf.time_array == uv.time_array)
    assert np.all(uvf.lst_array == uv.lst_array)
    assert np.all(uvf.freq_array == uv.freq_array)
    assert np.all(uvf.polarization_array == uv.polarization_array)
    assert np.all(uvf.baseline_array == uv.baseline_array)
    assert np.all(uvf.ant_1_array == uv.ant_1_array)
    assert np.all(uvf.ant_2_array == uv.ant_2_array)
    assert 'Flag object with type "baseline"' in uvf.history
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:telescope_location, antenna_positions")
def test_init_uvcal(uvcal_obj):
    uvc = uvcal_obj

    # add spectral windows to test handling
    uvc.Nspws = 2
    uvc.spw_array = np.array([0, 1])
    uvc.flex_spw_id_array = np.zeros(uvc.Nfreqs, dtype=int)
    uvc.flex_spw_id_array[: uvc.Nfreqs // 2] = 1
    uvc.check()

    uvf = UVFlag(uvc)
    assert uvf.metric_array.shape == uvc.flag_array.shape
    assert np.all(uvf.metric_array == 0)
    assert uvf.weights_array.shape == uvc.flag_array.shape
    assert np.all(uvf.weights_array == 1)
    assert uvf.type == "antenna"
    assert uvf.mode == "metric"
    assert np.all(uvf.time_array == uvc.time_array)
    assert np.all(uvf.telescope.feed_array == uvc.telescope.feed_array)
    assert np.all(uvf.telescope.feed_angle == uvc.telescope.feed_angle)
    assert np.all(uvf.lst_array == uvc.lst_array)
    assert np.all(uvf.freq_array == uvc.freq_array)
    assert np.all(uvf.polarization_array == uvc.jones_array)
    assert np.all(uvf.ant_array == uvc.ant_array)
    assert 'Flag object with type "antenna"' in uvf.history
    assert pyuvdata_version_str in uvf.history
    assert uvf.filename == uvc.filename


def test_init_uvcal_mode_flag(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc, copy_flags=False, mode="flag")
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None
    assert np.array_equal(uvf.flag_array, uvc.flag_array)

    assert uvf.weights_array is None
    assert uvf.type == "antenna"
    assert uvf.mode == "flag"
    assert np.all(uvf.time_array == uvc.time_array)
    assert np.all(uvf.lst_array == uvc.lst_array)
    assert np.all(uvf.freq_array == uvc.freq_array)
    assert np.all(uvf.polarization_array == uvc.jones_array)
    assert np.all(uvf.ant_array == uvc.ant_array)
    assert 'Flag object with type "antenna"' in uvf.history
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The shapes of several attributes will be changing")
@pytest.mark.filterwarnings("ignore:telescope_location, antenna_positions")
def test_init_cal_copy_flags(uvcal_obj):
    uv = uvcal_obj

    warn_type = [UserWarning]
    warn_msg = ['Copying flags to type=="antenna"']

    with check_warnings(warn_type, match=warn_msg):
        uvf = UVFlag(uv, copy_flags=True, mode="metric")
    #  with copy flags uvf.metric_array should be none
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None
    assert np.array_equal(uvf.flag_array, uv.flag_array)
    assert uvf.type == "antenna"
    assert uvf.mode == "flag"
    assert np.all(uvf.time_array == np.unique(uv.time_array))
    assert np.all(uvf.freq_array == uv.freq_array)

    assert np.all(uvf.polarization_array == uv.jones_array)
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_init_waterfall_uvd(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv, waterfall=True)
    assert uvf.metric_array.shape == (uv.Ntimes, uv.Nfreqs, uv.Npols)
    assert np.all(uvf.metric_array == 0)
    assert uvf.weights_array.shape == (uv.Ntimes, uv.Nfreqs, uv.Npols)
    assert np.all(uvf.weights_array == 1)
    assert uvf.type == "waterfall"
    assert uvf.mode == "metric"
    assert np.all(uvf.time_array == np.unique(uv.time_array))
    assert np.all(uvf.lst_array == np.unique(uv.lst_array))
    assert np.all(uvf.freq_array == uv.freq_array)
    assert np.all(uvf.polarization_array == uv.polarization_array)
    assert 'Flag object with type "waterfall"' in uvf.history
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The shapes of several attributes will be changing")
@pytest.mark.filterwarnings("ignore:telescope_location, antenna_positions")
def test_init_waterfall_uvc(uvcal_obj):
    uv = uvcal_obj

    uvf = UVFlag(uv, waterfall=True, history="input history check")
    assert uvf.metric_array.shape == (uv.Ntimes, uv.Nfreqs, uv.Njones)
    assert np.all(uvf.metric_array == 0)
    assert uvf.weights_array.shape == (uv.Ntimes, uv.Nfreqs, uv.Njones)
    assert np.all(uvf.weights_array == 1)
    assert uvf.type == "waterfall"
    assert uvf.mode == "metric"
    assert np.all(uvf.time_array == np.unique(uv.time_array))
    assert np.all(uvf.freq_array == uv.freq_array)
    assert np.all(uvf.polarization_array == uv.jones_array)
    assert 'Flag object with type "waterfall"' in uvf.history
    assert "input history check" in uvf.history
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:telescope_location, antenna_positions")
def test_init_waterfall_flag_uvcal(uvcal_obj):
    uv = uvcal_obj
    uvf = UVFlag(uv, waterfall=True, mode="flag")
    assert uvf.flag_array.shape == (uv.Ntimes, uv.Nfreqs, uv.Njones)
    assert not np.any(uvf.flag_array)
    assert uvf.weights_array is None
    assert uvf.type == "waterfall"
    assert uvf.mode == "flag"
    assert np.all(uvf.time_array == np.unique(uv.time_array))
    assert np.all(uvf.freq_array == uv.freq_array)
    assert np.all(uvf.polarization_array == uv.jones_array)
    assert 'Flag object with type "waterfall"' in uvf.history
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_init_waterfall_flag_uvdata(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv, waterfall=True, mode="flag")
    assert uvf.flag_array.shape == (uv.Ntimes, uv.Nfreqs, uv.Npols)
    assert not np.any(uvf.flag_array)
    assert uvf.weights_array is None
    assert uvf.type == "waterfall"
    assert uvf.mode == "flag"
    assert np.all(uvf.time_array == np.unique(uv.time_array))
    assert np.all(uvf.freq_array == uv.freq_array)
    assert np.all(uvf.polarization_array == uv.polarization_array)
    assert 'Flag object with type "waterfall"' in uvf.history
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.filterwarnings("ignore:telescope_location, antenna_positions")
def test_init_waterfall_copy_flags(uvdata_obj, uvcal_obj):
    uv = uvcal_obj
    with pytest.raises(
        NotImplementedError, match="Cannot copy flags when initializing"
    ):
        UVFlag(uv, copy_flags=True, mode="flag", waterfall=True)

    uv = uvdata_obj
    with pytest.raises(
        NotImplementedError, match="Cannot copy flags when initializing"
    ):
        UVFlag(uv, copy_flags=True, mode="flag", waterfall=True)


def test_init_invalid_input():
    # input is not UVData, UVCal, path, or list/tuple
    with pytest.raises(ValueError, match="input to UVFlag.__init__ must be one of:"):
        UVFlag(14)


def test_from_uvcal_error(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag()
    with pytest.raises(
        ValueError,
        match="from_uvcal can only initialize a UVFlag object from an input "
        "UVCal object or a subclass of a UVCal object.",
    ):
        uvf.from_uvcal(uv)

    delay_object = UVCal()
    delayfile = os.path.join(DATA_PATH, "zen.2457698.40355.xx.delay.calfits")

    # convert delay object to future array shapes, drop freq_array, set Nfreqs=1
    delay_object.read_calfits(delayfile)

    delay_object.freq_array = None
    delay_object.channel_width = None
    delay_object.Nfreqs = 1
    delay_object.check()

    with pytest.raises(
        ValueError,
        match="from_uvcal can only initialize a UVFlag object from a non-wide-band "
        "UVCal object.",
    ):
        uvf.from_uvcal(delay_object)


@pytest.mark.filterwarnings("ignore:telescope_location, antenna_positions")
def test_from_uvdata_error(uvcal_obj):
    uvf = UVFlag()
    with pytest.raises(
        ValueError, match="from_uvdata can only initialize a UVFlag object"
    ):
        uvf.from_uvdata(uvcal_obj)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_init_list_files_weights(tmpdir):
    # Test that weights are preserved when reading list of files
    tmp_path = tmpdir.strpath
    # Create two files to read
    uvf = UVFlag(test_f_file)
    np.random.seed(0)
    wts1 = np.random.rand(*uvf.weights_array.shape)
    uvf.weights_array = wts1.copy()
    uvf.write(os.path.join(tmp_path, "test1.h5"))
    wts2 = np.random.rand(*uvf.weights_array.shape)
    uvf.weights_array = wts2.copy()
    uvf.write(os.path.join(tmp_path, "test2.h5"))
    uvf2 = UVFlag(
        [os.path.join(tmp_path, "test1.h5"), os.path.join(tmp_path, "test2.h5")]
    )

    assert np.all(uvf2.weights_array == np.concatenate([wts1, wts2], axis=0))


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_init_posix():
    testfile_posix = pathlib.Path(test_f_file)
    uvf1 = UVFlag(test_f_file)
    uvf2 = UVFlag(testfile_posix)
    assert uvf1 == uvf2


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_hdf5_meta_telescope_location(test_outfile):
    meta = hdf5_utils.HDF5Meta(test_f_file)
    lat, lon, alt = meta.telescope_location_lat_lon_alt

    assert np.isclose(
        lat, meta.telescope_location_obj.lat.rad, rtol=0, atol=utils.RADIAN_TOL
    )
    assert np.isclose(
        lon, meta.telescope_location_obj.lon.rad, rtol=0, atol=utils.RADIAN_TOL
    )
    assert np.isclose(
        alt, meta.telescope_location_obj.height.to_value("m"), rtol=0, atol=1e-3
    )

    lat_deg, lon_deg, alt = meta.telescope_location_lat_lon_alt_degrees
    assert np.isclose(
        lat_deg,
        meta.telescope_location_obj.lat.deg,
        rtol=0,
        atol=np.rad2deg(utils.RADIAN_TOL),
    )
    assert np.isclose(
        lon_deg,
        meta.telescope_location_obj.lon.deg,
        rtol=0,
        atol=np.rad2deg(utils.RADIAN_TOL),
    )
    assert np.isclose(
        alt, meta.telescope_location_obj.height.to_value("m"), rtol=0, atol=1e-3
    )

    if len(frame_selenoid) > 1:
        from lunarsky import MoonLocation

        moon_loc = MoonLocation.from_selenodetic(
            lat * units.rad, lon * units.rad, alt * units.m
        )
        moon_xyz = np.array(
            [
                moon_loc.x.to_value("m"),
                moon_loc.y.to_value("m"),
                moon_loc.z.to_value("m"),
            ]
        )

        shutil.copyfile(test_f_file, test_outfile)
        with h5py.File(test_outfile, "r+") as h5f:
            h5f["Header/telescope_frame"] = "mcmf"
            del h5f["Header/telescope_location"]
            h5f["Header/telescope_location"] = moon_xyz

        meta = hdf5_utils.HDF5Meta(test_outfile)
        assert meta.telescope_frame == "mcmf"
        assert isinstance(meta.telescope_location_obj, MoonLocation)


@pytest.mark.skipif(
    len(frame_selenoid) > 1, reason="Test only when lunarsky not installed."
)
def test_hdf5_meta_no_moon(test_outfile, uvf_from_data):
    """Check errors when calling HDF5Meta with MCMF without lunarsky."""
    shutil.copyfile(test_f_file, test_outfile)
    with h5py.File(test_outfile, "r+") as h5f:
        h5f["Header/telescope_frame"] = "mcmf"

    meta = hdf5_utils.HDF5Meta(test_outfile)
    msg = "Need to install `lunarsky` package to work with selenoids or MCMF frame."
    with pytest.raises(ImportError, match=msg):
        meta.telescope_location_obj  # noqa: B018
    del meta

    uvf_from_data.write(test_outfile, clobber=True)
    with h5py.File(test_outfile, "r+") as h5f:
        del h5f["/Header/telescope_frame"]
        h5f["Header/telescope_frame"] = "mcmf"

    meta = hdf5_utils.HDF5Meta(test_outfile)
    with pytest.raises(ImportError, match=msg):
        meta.telescope_location_obj  # noqa: B018


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_data_like_property_mode_tamper(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.mode = "test"
    with pytest.raises(ValueError, match="Invalid mode. Mode must be one of"):
        list(uvf.data_like_parameters)


def test_read_write_loop(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")

    uvf.write(test_outfile, clobber=True)
    uvf2 = UVFlag(test_outfile)

    assert uvf.__eq__(uvf2, check_history=True)
    assert uvf2.filename == [os.path.basename(test_outfile)]


@pytest.mark.parametrize(["telescope_frame", "selenoid"], frame_selenoid)
def test_read_write_loop_spw(uvdata_obj, test_outfile, telescope_frame, selenoid):
    uv = uvdata_obj

    if telescope_frame == "mcmf":
        pytest.importorskip("lunarsky")
        from lunarsky import MoonLocation

        enu_antpos = uv.telescope.get_enu_antpos()
        uv.telescope.location = MoonLocation.from_selenodetic(
            lat=uv.telescope.location.lat,
            lon=uv.telescope.location.lon,
            height=uv.telescope.location.height,
            ellipsoid=selenoid,
        )
        new_full_antpos = utils.ECEF_from_ENU(
            enu=enu_antpos, center_loc=uv.telescope.location
        )
        uv.telescope.antenna_positions = new_full_antpos - uv.telescope._location.xyz()
        uv.set_lsts_from_time_array()
        uv.check()

    uvf = UVFlag(uv, label="test")

    uvf.Nspws = 2
    uvf.spw_array = np.array([0, 1])
    uvf.flex_spw_id_array = np.zeros(uv.Nfreqs, dtype=int)
    uvf.flex_spw_id_array[: uv.Nfreqs // 2] = 1
    uvf.check()

    uvf.write(test_outfile, clobber=True)
    uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)
    assert uvf2.filename == [os.path.basename(test_outfile)]

    meta = hdf5_utils.HDF5Meta(test_outfile)
    loc_obj = meta.telescope_location_obj

    assert np.isclose(loc_obj.x, uvf.telescope.location.x, rtol=0, atol=1e-3)
    assert np.isclose(loc_obj.y, uvf.telescope.location.y, rtol=0, atol=1e-3)
    assert np.isclose(loc_obj.z, uvf.telescope.location.z, rtol=0, atol=1e-3)


def test_read_write_loop_missing_shapes(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.write(test_outfile, clobber=True)
    with h5py.File(test_outfile, "r+") as h5f:
        del h5f["/Header/Ntimes"]
        del h5f["/Header/Nfreqs"]
        del h5f["/Header/Npols"]
        del h5f["/Header/Nblts"]
        del h5f["/Header/Nants_data"]
        del h5f["/Header/Nspws"]
    uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)
    assert uvf2.filename == [os.path.basename(test_outfile)]


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
@pytest.mark.parametrize(
    ["uvf_type", "param_list", "warn_type", "msg", "uv_mod"],
    [
        (
            "baseline",
            ["telescope_name"],
            [UserWarning],
            [
                "telescope_name not available in file, so telescope related parameters "
                "cannot be set. This will result in errors when the object is checked. "
                "To avoid the errors, either set the `telescope_name` parameter or use "
                "`run_check=False` to turn off the check."
            ],
            None,
        ),
        (
            "baseline",
            ["latitude", "longitude", "altitude"],
            None,
            "",
            "reset_telescope_params",
        ),
        ("baseline", ["antenna_names"], None, "", "reset_telescope_params"),
        (
            "baseline",
            ["antenna_names"],
            UserWarning,
            [
                "Not all antennas have metadata in the known_telescope data. "
                "Not setting ['antenna_names']",
                "antenna_names not in file, setting based on antenna_numbers",
            ],
            "change_ant_numbers",
        ),
        ("baseline", ["antenna_numbers"], None, "", "reset_telescope_params"),
        ("baseline", ["antenna_positions"], None, "", "reset_telescope_params"),
        ("baseline", ["Nants_telescope"], None, [], "reset_telescope_params"),
        (
            "waterfall",
            ["Nants_telescope", "telescope_name", "antenna_numbers"],
            [UserWarning],
            [
                "telescope_name not available in file, so telescope related parameters "
                "cannot be set. This will result in errors when the object is checked. "
                "To avoid the errors, either set the `telescope_name` parameter or use "
                "`run_check=False` to turn off the check."
            ],
            None,
        ),
        (
            "waterfall",
            ["Nants_telescope", "telescope_name", "antenna_numbers", "antenna_names"],
            [UserWarning],
            [
                "telescope_name not available in file, so telescope related parameters "
                "cannot be set. This will result in errors when the object is checked. "
                "To avoid the errors, either set the `telescope_name` parameter or use "
                "`run_check=False` to turn off the check."
            ],
            None,
        ),
        (
            "waterfall",
            [
                "Nants_telescope",
                "telescope_name",
                "antenna_numbers",
                "antenna_names",
                "antenna_positions",
            ],
            [UserWarning],
            [
                "telescope_name not available in file, so telescope related parameters "
                "cannot be set. This will result in errors when the object is checked. "
                "To avoid the errors, either set the `telescope_name` parameter or use "
                "`run_check=False` to turn off the check."
            ],
            None,
        ),
        (
            "baseline",
            ["antenna_names", "antenna_numbers", "antenna_positions"],
            None,
            "",
            "reset_telescope_params",
        ),
        (
            "baseline",
            ["antenna_numbers"],
            [UserWarning, UserWarning],
            [
                "Not all antennas have metadata in the known_telescope data. "
                "Not setting ['antenna_numbers'].",
                "antenna_numbers not in file, cannot be set based on ant_1_array and "
                "ant_2_array because Nants_telescope is greater than Nants_data.",
            ],
            None,
        ),
        ("baseline", ["antenna_names"], None, "", None),
        (
            "baseline",
            ["antenna_numbers"],
            UserWarning,
            [
                "Not all antennas have metadata in the known_telescope data. "
                "Not setting ['antenna_numbers']",
                "antenna_numbers not in file, setting based on ant_1_array and "
                "ant_2_array.",
            ],
            "remove_extra_metadata",
        ),
        (
            "antenna",
            ["antenna_numbers"],
            [UserWarning, UserWarning],
            [
                "Not all antennas have metadata in the known_telescope data. "
                "Not setting ['antenna_numbers']",
                "antenna_numbers not in file, cannot be set based on ant_array because "
                "Nants_telescope is greater than Nants_data.",
            ],
            None,
        ),
        (
            "antenna",
            ["antenna_numbers"],
            [UserWarning, UserWarning],
            [
                "Not all antennas have metadata in the known_telescope data. "
                "Not setting ['antenna_numbers']",
                "antenna_numbers not in file, setting based on ant_array.",
            ],
            "remove_extra_metadata",
        ),
        (
            "antenna",
            ["antenna_numbers"],
            [UserWarning, UserWarning],
            [
                "Not all antennas have metadata in the known_telescope data. "
                "Not setting ['antenna_numbers']",
                "antenna_numbers not in file, cannot be set based on ant_array "
                "because Nants_telescope is greater than Nants_data. This will result "
                "in errors when the object is checked.",
            ],
            "change_ant_numbers",
        ),
    ],
)
def test_read_write_loop_missing_telescope_info(
    uvdata_obj_weird_telparams,
    test_outfile,
    uvf_type,
    param_list,
    warn_type,
    msg,
    uv_mod,
):
    if uvf_type == "antenna":
        uv = UVCal()
        uv.read_calfits(test_c_file)
    else:
        uv = uvdata_obj_weird_telparams

    run_check = True

    if uv_mod == "reset_telescope_params":
        with check_warnings(
            UserWarning,
            match="telescope_location, Nants, antenna_names, antenna_numbers, "
            "antenna_positions, mount_type, antenna_diameters are not set or are being "
            "overwritten. telescope_location, Nants, antenna_names, "
            "antenna_numbers, antenna_positions, mount_type, antenna_diameters are set "
            "using values from known telescopes for HERA.",
        ):
            uv.set_telescope_params(overwrite=True)
    elif uv_mod == "remove_extra_metadata":
        if uvf_type == "antenna":
            ant_inds_keep = np.nonzero(
                np.isin(uv.telescope.antenna_numbers, uv.ant_array)
            )[0]
            uv.telescope._select_along_param_axis({"Nants": ant_inds_keep})
            uv.check()
        else:
            uv.select(
                antenna_nums=np.union1d(uv.ant_1_array, uv.ant_2_array),
                keep_all_metadata=False,
            )
    elif uv_mod == "change_ant_numbers":
        run_check = False
        if uvf_type == "antenna":
            max_ant = np.max(uv.ant_array)
            new_max = max_ant + 300
            uv.ant_array[np.nonzero(uv.ant_array == max_ant)[0]] = new_max
            uv.telescope.antenna_numbers[
                np.nonzero(uv.telescope.antenna_numbers == max_ant)[0]
            ] = new_max
        else:
            max_ant = np.max(np.union1d(uv.ant_1_array, uv.ant_2_array))
            new_max = max_ant + 300
            uv.ant_1_array[np.nonzero(uv.ant_1_array == max_ant)[0]] = new_max
            uv.ant_2_array[np.nonzero(uv.ant_2_array == max_ant)[0]] = new_max
            uv.telescope.antenna_numbers[
                np.nonzero(uv.telescope.antenna_numbers == max_ant)[0]
            ] = new_max
    else:
        run_check = False

    uvf = UVFlag(uv, label="test")
    if uvf_type == "waterfall":
        uvf.to_waterfall()

    uvf.write(test_outfile, clobber=True)
    with h5py.File(test_outfile, "r+") as h5f:
        for param in param_list:
            del h5f["/Header/" + param]

    if "telescope_name" in param_list:
        run_check = False

    with check_warnings(warn_type, match=None if warn_type is None else msg):
        uvf2 = UVFlag(test_outfile, run_check=run_check)

    if uv_mod is None:
        if param_list == ["antenna_names"]:
            assert not np.array_equal(
                uvf2.telescope.antenna_names, uvf.telescope.antenna_names
            )
            uvf2.telescope.antenna_names = uvf.telescope.antenna_names
        else:
            telescope_params = {
                "telescope_name": "name",
                "telescope_location": "location",
                "Nants_telescope": "Nants",
                "antenna_names": "antenna_names",
                "antenna_numbers": "antenna_numbers",
                "antenna_positions": "antenna_positions",
                "antenna_diameters": "antenna_diameters",
                "feed_array": "feed_array",
                "feed_angle": "feed_angle",
                "mount_type": "mount_type",
                "instrument": "instrument",
            }
            for param in param_list:
                tel_param = telescope_params[param]
                if param != "Nants_telescope":
                    assert getattr(uvf2.telescope, tel_param) is None
                setattr(uvf2.telescope, tel_param, getattr(uv.telescope, tel_param))
    elif "telescope_name" in param_list:
        assert uvf2.telescope.name is None
        uvf2.telescope.name = uvf.telescope.name
    if uv_mod != "change_ant_numbers":
        assert uvf.__eq__(uvf2, check_history=True)
        assert uvf2.filename == [os.path.basename(test_outfile)]

    if "telescope_name" in param_list and "Nants_telescope" not in param_list:
        uvf2 = UVFlag(test_outfile, telescope_name="HERA")
        assert uvf.__eq__(uvf2, check_history=True)
        assert uvf2.filename == [os.path.basename(test_outfile)]

    if "Nants_telescope" in param_list and "telescope_name" not in param_list:
        with check_warnings(
            UserWarning,
            match=([] if warn_type is None else [msg])
            + [
                "Telescope_name parameter is set to foo, which overrides the telescope "
                "name in the file (HERA)."
            ],
        ):
            uvf2 = UVFlag(test_outfile, telescope_name="foo")


def test_missing_telescope_info_mwa(test_outfile):
    mwa_uvfits = os.path.join(DATA_PATH, "1133866760.uvfits")
    metafits = os.path.join(DATA_PATH, "mwa_corr_fits_testfiles", "1131733552.metafits")
    with check_warnings(
        UserWarning, match="Fixing auto-correlations to be be real-only"
    ):
        uvd = UVData.from_file(mwa_uvfits)
    uvf = UVFlag(uvd, waterfall=True)

    uvf.write(test_outfile, clobber=True)
    param_list = [
        "telescope_name",
        "antenna_numbers",
        "antenna_names",
        "antenna_positions",
        "Nants_telescope",
    ]
    with h5py.File(test_outfile, "r+") as h5f:
        for param in param_list:
            del h5f["/Header/" + param]

    with check_warnings(
        UserWarning,
        match=[
            "Antenna metadata are missing for this file. Since this is MWA data, the "
            "best way to fill in these metadata is to pass in an mwa_metafits_file "
            "which contains information about which antennas were connected when the "
            "data were taken. Since that was not passed, the antenna metadata will be "
            "filled in from a static csv file containing all the antennas that could "
            "have been connected."
        ],
    ):
        uvf2 = UVFlag(test_outfile, telescope_name="mwa")

    from pyuvdata.uvdata.mwa_corr_fits import read_metafits

    with pytest.raises(
        ValueError,
        match="mwax, flag_init, start_flag and start_time must all be passed if the "
        "`telescope_info_only` parameter is False",
    ):
        read_metafits(metafits)

    uvf.write(test_outfile, clobber=True)
    param_list = [
        "telescope_name",
        "antenna_numbers",
        "antenna_positions",
        "Nants_telescope",
    ]
    with h5py.File(test_outfile, "r+") as h5f:
        for param in param_list:
            del h5f["/Header/" + param]

    with check_warnings(
        UserWarning,
        match=[
            "An mwa_metafits_file was passed. The metadata from the metafits file are "
            "overriding the following parameters in the UVFlag file: "
            "['antenna_names', 'telescope_location']",
            "The lst_array is not self-consistent with the time_array and telescope "
            "location. Consider recomputing with the `set_lsts_from_time_array` method",
        ],
    ):
        uvf3 = UVFlag(test_outfile, mwa_metafits_file=metafits)

    assert uvf2.telescope.Nants > uvf3.telescope.Nants


def test_read_write_loop_wrong_nants_data(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.write(test_outfile, clobber=True)
    with h5py.File(test_outfile, "r+") as h5f:
        nants_data = int(h5f["/Header/Nants_data"][()])
        del h5f["/Header/Nants_data"]
        h5f["Header/Nants_data"] = nants_data - 1

    with check_warnings(
        UserWarning,
        match="Nants_data in file does not match number of antennas with data. "
        "Resetting Nants_data.",
    ):
        uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)
    assert uvf2.filename == [os.path.basename(test_outfile)]


def test_read_write_loop_mucked_channel_width(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.write(test_outfile, clobber=True)
    with h5py.File(test_outfile, "r+") as h5f:
        del h5f["/Header/channel_width"]
    with check_warnings(
        UserWarning,
        match="channel_width not available in file, computing it from the freq_array "
        "spacing.",
    ):
        uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)
    assert uvf2.filename == [os.path.basename(test_outfile)]

    uvf.write(test_outfile, clobber=True)
    with h5py.File(test_outfile, "r+") as h5f:
        del h5f["/Header/channel_width"]
        h5f["/Header/channel_width"] = uvf.channel_width[0]

    uvf2 = UVFlag(test_outfile)
    assert uvf == uvf2

    uvf.freq_array[0] -= uvf.channel_width[0]
    uvf.channel_width[0] *= 2

    uvf.write(test_outfile, clobber=True)
    with h5py.File(test_outfile, "r+") as h5f:
        del h5f["/Header/channel_width"]
    with check_warnings(
        UserWarning,
        match="channel_width not available in file, computing it from the freq_array "
        "spacing. The freq_array does not have equal spacing, so the last "
        "channel_width is set equal to the channel width below it.",
    ):
        uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)
    assert uvf2.filename == [os.path.basename(test_outfile)]


def test_read_write_loop_missing_spw_array(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.write(test_outfile, clobber=True)
    with h5py.File(test_outfile, "r+") as h5f:
        del h5f["/Header/spw_array"]
    uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)
    assert uvf2.filename == [os.path.basename(test_outfile)]


def test_read_write_loop_with_optional_x_orientation(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.telescope.set_feeds_from_x_orientation(
        "east", polarization_array=uvf.polarization_array
    )
    uvf.write(test_outfile, clobber=True)
    uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)


@pytest.mark.parametrize("spw_axis", [True, False])
def test_read_write_loop_waterfall(uvdata_obj, test_outfile, spw_axis):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.to_waterfall()
    uvf.write(test_outfile, clobber=True)

    if spw_axis:
        # mock an old file weirdness
        with h5py.File(test_outfile, "r+") as h5f:
            freq_array = h5f["/Header/freq_array"][()]
            del h5f["/Header/freq_array"]
            h5f["/Header/freq_array"] = freq_array[np.newaxis, :]

    uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_read_write_loop_ret_wt_sq(test_outfile):
    uvf = UVFlag(test_f_file)
    uvf.weights_array = 2 * np.ones_like(uvf.weights_array)
    uvf.to_waterfall(return_weights_square=True)
    uvf.write(test_outfile, clobber=True)
    uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)


def test_bad_mode_savefile(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")

    # create the file so the clobber gets tested
    with h5py.File(test_outfile, "w") as h5file:
        h5file.create_dataset("Test", list(range(10)))

    uvf.write(test_outfile, clobber=True)
    # manually re-read and tamper with parameters
    with h5py.File(test_outfile, "a") as h5:
        mode = h5["Header/mode"]
        mode[...] = np.bytes_("test")

    with pytest.raises(ValueError, match="File cannot be read. Received mode"):
        uvf = UVFlag(test_outfile)


def test_bad_type_savefile(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.write(test_outfile, clobber=True)
    # manually re-read and tamper with parameters
    with h5py.File(test_outfile, "a") as h5:
        mode = h5["Header/type"]
        mode[...] = np.bytes_("test")

    with pytest.raises(ValueError, match="File cannot be read. Received type"):
        uvf = UVFlag(test_outfile)


def test_write_add_version_str(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.history = uvf.history.replace(pyuvdata_version_str, "")

    assert pyuvdata_version_str not in uvf.history
    uvf.write(test_outfile, clobber=True)

    with h5py.File(test_outfile, "r") as h5:
        assert h5["Header/history"].dtype.type is np.bytes_
        hist = h5["Header/history"][()].decode("utf8")
    assert pyuvdata_version_str in hist


def test_read_add_version_str(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")

    assert pyuvdata_version_str in uvf.history
    uvf.write(test_outfile, clobber=True)

    with h5py.File(test_outfile, "r") as h5:
        hist = h5["Header/history"]
        del hist

    uvf2 = UVFlag(test_outfile)
    assert pyuvdata_version_str in uvf2.history
    assert uvf == uvf2


@pytest.mark.parametrize("existing", [True, False])
def test_read_write_ant(uvcal_obj, test_outfile, existing):
    uvc = uvcal_obj
    uvf = UVFlag(uvc, mode="flag", label="test")
    uvf.write(test_outfile, clobber=True)

    if existing:
        uvf2 = uvf.copy()
        uvf2.read(test_outfile)
    else:
        uvf2 = UVFlag(test_outfile)

    assert uvf.__eq__(uvf2, check_history=True)


@pytest.mark.filterwarnings("ignore:telescope_location, antenna_positions")
def test_read_missing_nants_data(test_outfile, uvcal_obj):
    uv = uvcal_obj
    uvf = UVFlag(uv, mode="flag", label="test")
    uvf.write(test_outfile, clobber=True)

    with h5py.File(test_outfile, "a") as h5:
        del h5["Header/Nants_data"]

    uvf2 = UVFlag(test_outfile)

    # make sure this was set to None
    assert uvf2.Nants_data == len(uvf2.ant_array)

    uvf2.Nants_data = uvf.Nants_data
    # verify no other elements were changed
    assert uvf.__eq__(uvf2, check_history=True)


@pytest.mark.filterwarnings("ignore:telescope_location, antenna_positions")
def test_read_missing_nspws(test_outfile, uvcal_obj):
    uv = uvcal_obj
    uvf = UVFlag(uv, mode="flag", label="test")
    uvf.write(test_outfile, clobber=True)

    with h5py.File(test_outfile, "a") as h5:
        del h5["Header/Nspws"]

    uvf2 = UVFlag(test_outfile)
    # make sure Nspws was calculated
    assert uvf2.Nspws == 1

    # verify no other elements were changed
    assert uvf.__eq__(uvf2, check_history=True)


def test_read_write_nocompress(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.write(test_outfile, clobber=True, data_compression=None)
    uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)


def test_read_write_nocompress_flag(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, mode="flag", label="test")
    uvf.write(test_outfile, clobber=True, data_compression=None)
    uvf2 = UVFlag(test_outfile)
    assert uvf.__eq__(uvf2, check_history=True)


def test_read_write_extra_keywords(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, label="test")
    uvf.extra_keywords = {"keyword1": 1, "keyword2": "string"}
    uvf.write(test_outfile, clobber=True, data_compression=None)
    uvf2 = UVFlag(test_outfile)
    assert uvf2.extra_keywords["keyword1"] == 1
    assert uvf2.extra_keywords["keyword2"] == "string"


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_init_list(uvdata_obj):
    uv = uvdata_obj
    uv.time_array -= 1
    uv.set_lsts_from_time_array()
    with check_warnings(
        UserWarning,
        match=[
            "UVParameter Telescope.instrument does not match. Continuing anyways.",
            "UVParameter Telescope.antenna_diameters does not match. Continuing anyway",
            "UVParameter Telescope.mount_type does not match. Continuing anyways.",
        ],
    ):
        uvf = UVFlag([uv, test_f_file])
    uvf1 = UVFlag(uv)
    uvf2 = UVFlag(test_f_file)

    uv.telescope.location = uvf2.telescope.location
    uv.telescope.antenna_names = uvf2.telescope.antenna_names

    assert np.array_equal(
        np.concatenate((uvf1.metric_array, uvf2.metric_array), axis=0), uvf.metric_array
    )
    assert np.array_equal(
        np.concatenate((uvf1.weights_array, uvf2.weights_array), axis=0),
        uvf.weights_array,
    )
    assert np.array_equal(
        np.concatenate((uvf1.time_array, uvf2.time_array)), uvf.time_array
    )
    assert np.array_equal(
        np.concatenate((uvf1.baseline_array, uvf2.baseline_array)), uvf.baseline_array
    )
    assert np.array_equal(
        np.concatenate((uvf1.ant_1_array, uvf2.ant_1_array)), uvf.ant_1_array
    )
    assert np.array_equal(
        np.concatenate((uvf1.ant_2_array, uvf2.ant_2_array)), uvf.ant_2_array
    )
    assert uvf.mode == "metric"
    assert np.all(uvf.freq_array == uv.freq_array)
    assert np.all(uvf.polarization_array == uv.polarization_array)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_read_multiple_files(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uv.time_array -= 1
    uv.set_lsts_from_time_array()
    uvf = UVFlag(uv)
    uvf.write(test_outfile, clobber=True)

    warn_msg = [
        "UVParameter Telescope.instrument does not match. Continuing anyways.",
        "UVParameter Telescope.antenna_diameters does not match. Continuing anyways.",
        "UVParameter Telescope.mount_type does not match. Continuing anyways.",
    ]
    warn_type = [UserWarning] * 3

    with check_warnings(warn_type, match=warn_msg):
        uvf.read([test_outfile, test_f_file])
    assert uvf.filename == sorted(
        os.path.basename(file) for file in [test_outfile, test_f_file]
    )

    uvf1 = UVFlag(uv)
    uvf2 = UVFlag(test_f_file)
    assert np.array_equal(
        np.concatenate((uvf1.metric_array, uvf2.metric_array), axis=0), uvf.metric_array
    )
    assert np.array_equal(
        np.concatenate((uvf1.weights_array, uvf2.weights_array), axis=0),
        uvf.weights_array,
    )
    assert np.array_equal(
        np.concatenate((uvf1.time_array, uvf2.time_array)), uvf.time_array
    )
    assert np.array_equal(
        np.concatenate((uvf1.baseline_array, uvf2.baseline_array)), uvf.baseline_array
    )
    assert np.array_equal(
        np.concatenate((uvf1.ant_1_array, uvf2.ant_1_array)), uvf.ant_1_array
    )
    assert np.array_equal(
        np.concatenate((uvf1.ant_2_array, uvf2.ant_2_array)), uvf.ant_2_array
    )
    assert uvf.mode == "metric"
    assert np.all(uvf.freq_array == uv.freq_array)
    assert np.all(uvf.polarization_array == uv.polarization_array)


def test_read_error():
    with pytest.raises(IOError, match="foo not found"):
        UVFlag("foo")


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_read_change_type(uvcal_obj, test_outfile):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)

    uvf.write(test_outfile, clobber=True)
    assert hasattr(uvf, "ant_array")
    uvf.read(test_f_file)

    # clear sets these to None now
    assert hasattr(uvf, "ant_array")
    assert uvf.ant_array is None
    assert hasattr(uvf, "baseline_array")
    assert hasattr(uvf, "ant_1_array")
    assert hasattr(uvf, "ant_2_array")
    uvf.read(test_outfile)
    assert hasattr(uvf, "ant_array")
    assert hasattr(uvf, "baseline_array")
    assert uvf.baseline_array is None
    assert hasattr(uvf, "ant_1_array")
    assert uvf.ant_1_array is None
    assert hasattr(uvf, "ant_2_array")
    assert uvf.ant_2_array is None


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_read_change_mode(uvdata_obj, test_outfile):
    uv = uvdata_obj
    uvf = UVFlag(uv, mode="flag")
    assert hasattr(uvf, "flag_array")
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None
    uvf.write(test_outfile, clobber=True)
    uvf.read(test_f_file)
    assert hasattr(uvf, "metric_array")
    assert hasattr(uvf, "flag_array")
    assert uvf.flag_array is None
    uvf.read(test_outfile)
    assert hasattr(uvf, "flag_array")
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_write_no_clobber():
    uvf = UVFlag(test_f_file)
    with pytest.raises(ValueError, match=re.escape("File " + test_f_file + " exists")):
        uvf.write(test_f_file)


@pytest.mark.parametrize("background", [True, False])
def test_set_lsts(uvf_from_data, background):
    uvf = uvf_from_data

    uvf2 = uvf.copy()
    proc = uvf2.set_lsts_from_time_array(background=background)

    if proc is not None:
        proc.join()

    assert uvf2._lst_array == uvf._lst_array


def test_set_telescope_params(uvdata_obj):
    uvd = uvdata_obj
    uvd.set_telescope_params(overwrite=True, warn=False)
    ants_with_data = np.union1d(uvd.ant_1_array, uvd.ant_2_array)
    uvd2 = uvd.select(
        antenna_nums=ants_with_data[: uvd.Nants_data // 2],
        keep_all_metadata=False,
        inplace=False,
    )
    uvf = UVFlag(uvd2)
    # the telescope objects aren't equal because they have different sets of
    # required parameters (UVData's requires instrument while UVFlag's does not)
    # so just test the relevant attributes
    assert uvf.telescope._antenna_names == uvd2.telescope._antenna_names
    assert uvf.telescope._antenna_numbers == uvd2.telescope._antenna_numbers
    assert uvf.telescope._antenna_positions == uvd2.telescope._antenna_positions

    uvf.set_telescope_params(overwrite=True, warn=False)
    assert uvf.telescope._antenna_names == uvd.telescope._antenna_names
    assert uvf.telescope._antenna_numbers == uvd.telescope._antenna_numbers
    assert uvf.telescope._antenna_positions == uvd.telescope._antenna_positions

    uvf = UVFlag(uvd2)
    uvf.telescope.antenna_positions = None
    uvf.set_telescope_params()

    uvf = UVFlag(uvd2)
    uvf.telescope.name = "foo"
    uvf.telescope.location = None
    with pytest.raises(
        ValueError,
        match="Telescope foo is not in astropy_sites or known_telescopes_dict.",
    ):
        uvf.set_telescope_params()


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_add():
    uv1 = UVFlag(test_f_file)
    uv2 = copy.copy(uv1)
    uv2.time_array += 1  # Add a day
    with check_warnings(
        UserWarning,
        match="The lst_array is not self-consistent with the time_array and "
        "telescope location. Consider recomputing with the "
        "`set_lsts_from_time_array` method.",
    ):
        uv2.check()

    uv2.set_lsts_from_time_array()
    uv3 = uv1 + uv2
    assert np.array_equal(
        np.concatenate((uv1.time_array, uv2.time_array)), uv3.time_array
    )
    assert np.array_equal(
        np.concatenate((uv1.baseline_array, uv2.baseline_array)), uv3.baseline_array
    )
    assert np.array_equal(
        np.concatenate((uv1.ant_1_array, uv2.ant_1_array)), uv3.ant_1_array
    )
    assert np.array_equal(
        np.concatenate((uv1.ant_2_array, uv2.ant_2_array)), uv3.ant_2_array
    )
    assert np.array_equal(np.concatenate((uv1.lst_array, uv2.lst_array)), uv3.lst_array)
    assert np.array_equal(
        np.concatenate((uv1.metric_array, uv2.metric_array), axis=0), uv3.metric_array
    )
    assert np.array_equal(
        np.concatenate((uv1.weights_array, uv2.weights_array), axis=0),
        uv3.weights_array,
    )
    assert np.array_equal(uv1.freq_array, uv3.freq_array)
    assert uv3.type == "baseline"
    assert uv3.mode == "metric"
    assert np.array_equal(uv1.polarization_array, uv3.polarization_array)
    assert "Data combined along time axis. " in uv3.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_add_collapsed_pols():
    uvf = UVFlag(test_f_file)
    uvf.weights_array = np.ones_like(uvf.weights_array)
    uvf2 = uvf.copy()
    uvf2.polarization_array[0] = -4
    uvf.__add__(uvf2, inplace=True, axis="pol")  # Concatenate to form multi-pol object
    uvf.collapse_pol()
    uvf3 = uvf.copy()
    uvf3.time_array += 1  # increment the time array
    uvf3.set_lsts_from_time_array()
    uvf4 = uvf + uvf3
    assert uvf4.Ntimes == 2 * uvf.Ntimes
    uvf4.check()


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_add_add_version_str():
    uv1 = UVFlag(test_f_file)
    uv1.history = uv1.history.replace(pyuvdata_version_str, "")

    assert pyuvdata_version_str not in uv1.history

    uv2 = uv1.copy()
    uv2.time_array += 1  # Add a day
    uv2.set_lsts_from_time_array()
    uv3 = uv1 + uv2
    assert pyuvdata_version_str in uv3.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_add_baseline():
    uv1 = UVFlag(test_f_file)
    uv2 = uv1.copy()
    uv2.baseline_array += 100  # Arbitrary
    uv3 = uv1.__add__(uv2, axis="baseline")
    assert np.array_equal(
        np.concatenate((uv1.time_array, uv2.time_array)), uv3.time_array
    )
    assert np.array_equal(
        np.concatenate((uv1.baseline_array, uv2.baseline_array)), uv3.baseline_array
    )
    assert np.array_equal(
        np.concatenate((uv1.ant_1_array, uv2.ant_1_array)), uv3.ant_1_array
    )
    assert np.array_equal(
        np.concatenate((uv1.ant_2_array, uv2.ant_2_array)), uv3.ant_2_array
    )
    assert np.array_equal(np.concatenate((uv1.lst_array, uv2.lst_array)), uv3.lst_array)
    assert np.array_equal(
        np.concatenate((uv1.metric_array, uv2.metric_array), axis=0), uv3.metric_array
    )
    assert np.array_equal(
        np.concatenate((uv1.weights_array, uv2.weights_array), axis=0),
        uv3.weights_array,
    )
    assert np.array_equal(uv1.freq_array, uv3.freq_array)
    assert uv3.type == "baseline"
    assert uv3.mode == "metric"
    assert np.array_equal(uv1.polarization_array, uv3.polarization_array)
    assert "Data combined along baseline axis. " in uv3.history


@pytest.mark.parametrize("diameters", ["both", "left", "right"])
def test_add_antenna(uvcal_obj, diameters):
    uvc = uvcal_obj
    uv1 = UVFlag(uvc)
    uv2 = uv1.copy()
    uv2.ant_array += 100  # Arbitrary
    uv2.telescope.antenna_numbers += 100
    uv2.telescope.antenna_names = np.array(
        [name + "_new" for name in uv2.telescope.antenna_names]
    )
    if diameters == "left" or diameters == "right":
        uv2.telescope.antenna_diameters = None
        uv2.telescope.feed_array = None
        uv2.telescope.feed_angle = None
        uv2.telescope.mount_type = None

    if diameters == "both":
        warn_type = UserWarning
        warn_msg = [
            "UVParameter Telescope.antenna_names does not match. Continuing anyway.",
            "UVParameter Telescope.antenna_positions does not match. Continuing anyway",
        ]
    else:
        warn_type = UserWarning
        warn_msg = [
            "UVParameter Telescope.antenna_names does not match. Continuing anyway.",
            "UVParameter Telescope.antenna_positions does not match. Continuing anyway",
            "UVParameter Telescope.antenna_diameters does not match. Continuing anyway",
            "UVParameter Telescope.feed_array does not match. Continuing anyway.",
            "UVParameter Telescope.feed_angle does not match. Continuing anyway.",
            "UVParameter Telescope.mount_type does not match. Continuing anyway.",
        ]

    with check_warnings(warn_type, match=warn_msg):
        uv3 = uv1.__add__(uv2, axis="antenna")

    if diameters != "both":
        assert uv3.telescope.antenna_diameters is None
        assert uv3.telescope.feed_array is None
        assert uv3.telescope.feed_angle is None
        assert uv3.telescope.mount_type is None

    assert np.array_equal(np.concatenate((uv1.ant_array, uv2.ant_array)), uv3.ant_array)
    assert np.array_equal(
        np.concatenate((uv1.metric_array, uv2.metric_array), axis=0), uv3.metric_array
    )
    assert np.array_equal(
        np.concatenate((uv1.weights_array, uv2.weights_array), axis=0),
        uv3.weights_array,
    )
    assert np.array_equal(uv1.freq_array, uv3.freq_array)
    assert np.array_equal(uv1.time_array, uv3.time_array)
    assert np.array_equal(uv1.lst_array, uv3.lst_array)
    assert uv3.type == "antenna"
    assert uv3.mode == "metric"
    assert np.array_equal(uv1.polarization_array, uv3.polarization_array)
    assert "Data combined along antenna axis. " in uv3.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_add_frequency():
    uv1 = UVFlag(test_f_file)
    uv2 = uv1.copy()
    uv2.freq_array += 1e4  # Arbitrary

    uv3 = uv1.__add__(uv2, axis="frequency")
    assert np.array_equal(
        np.concatenate((uv1.freq_array, uv2.freq_array), axis=-1), uv3.freq_array
    )
    assert np.array_equal(uv1.time_array, uv3.time_array)
    assert np.array_equal(uv1.baseline_array, uv3.baseline_array)
    assert np.array_equal(uv1.ant_1_array, uv3.ant_1_array)
    assert np.array_equal(uv1.ant_2_array, uv3.ant_2_array)
    assert np.array_equal(uv1.lst_array, uv3.lst_array)
    assert np.array_equal(
        np.concatenate((uv1.metric_array, uv2.metric_array), axis=1), uv3.metric_array
    )
    assert np.array_equal(
        np.concatenate((uv1.weights_array, uv2.weights_array), axis=1),
        uv3.weights_array,
    )
    assert uv3.type == "baseline"
    assert uv3.mode == "metric"
    assert np.array_equal(uv1.polarization_array, uv3.polarization_array)
    assert "Data combined along frequency axis. " in uv3.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
@pytest.mark.parametrize("split_spw", [True, False])
def test_add_frequency_multi_spw(split_spw):
    uv1 = UVFlag(test_f_file)

    # add spectral windows to test handling
    uv1.Nspws = 2
    uv1.spw_array = np.array([0, 1])
    uv1.flex_spw_id_array = np.zeros(uv1.Nfreqs, dtype=int)
    uv1.flex_spw_id_array[uv1.Nfreqs // 2 :] = 1
    uv1.check()

    uv2 = uv1.copy()
    uv_full = uv1.copy()

    if split_spw:
        uv1.select(freq_chans=np.arange(uv1.Nfreqs // 3))
        uv2.select(freq_chans=np.arange(uv2.Nfreqs // 3, uv2.Nfreqs))
    else:
        uv1.select(freq_chans=np.arange(uv1.Nfreqs // 2))
        assert uv1.Nspws == 1
        assert uv1.Nfreqs == uv_full.Nfreqs // 2
        uv2.select(freq_chans=np.arange(uv2.Nfreqs // 2, uv2.Nfreqs))
        assert uv2.Nspws == 1
        assert uv2.Nfreqs == uv_full.Nfreqs // 2

        with check_warnings(None):
            uv1.check()
            uv2.check()

    uv3 = uv1.__add__(uv2, axis="frequency")
    assert uv3.history != uv_full.history
    uv3.history = uv_full.history

    assert uv3 == uv_full


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_add_frequency_with_weights_square():
    # Same test as above, just checking an optional parameter (also in waterfall mode)
    uvf1 = UVFlag(test_f_file)
    uvf1.weights_array = 2 * np.ones_like(uvf1.weights_array)
    uvf1.to_waterfall(return_weights_square=True)
    uvf2 = uvf1.copy()
    uvf2.freq_array += 1e4
    uvf3 = uvf1.__add__(uvf2, axis="frequency")
    assert np.array_equal(
        np.concatenate((uvf1.weights_square_array, uvf2.weights_square_array), axis=1),
        uvf3.weights_square_array,
    )


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_add_frequency_mix_weights_square():
    # Same test as above, checking some error handling
    uvf1 = UVFlag(test_f_file)
    uvf1.weights_array = 2 * np.ones_like(uvf1.weights_array)
    uvf2 = uvf1.copy()
    uvf1.to_waterfall(return_weights_square=True)
    uvf2.to_waterfall(return_weights_square=False)
    uvf2.freq_array += 1e4
    with pytest.raises(
        ValueError,
        match="weights_square_array optional parameter is missing from second UVFlag",
    ):
        uvf1.__add__(uvf2, axis="frequency", inplace=True)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_add_pol():
    uv1 = UVFlag(test_f_file)
    uv2 = uv1.copy()
    uv2.polarization_array += 1  # Arbitrary
    uv3 = uv1.__add__(uv2, axis="polarization")
    assert np.array_equal(uv1.freq_array, uv3.freq_array)
    assert np.array_equal(uv1.time_array, uv3.time_array)
    assert np.array_equal(uv1.baseline_array, uv3.baseline_array)
    assert np.array_equal(uv1.ant_1_array, uv3.ant_1_array)
    assert np.array_equal(uv1.ant_2_array, uv3.ant_2_array)
    assert np.array_equal(uv1.lst_array, uv3.lst_array)
    assert np.array_equal(
        np.concatenate((uv1.metric_array, uv2.metric_array), axis=2), uv3.metric_array
    )
    assert np.array_equal(
        np.concatenate((uv1.weights_array, uv2.weights_array), axis=2),
        uv3.weights_array,
    )
    assert uv3.type == "baseline"
    assert uv3.mode == "metric"
    assert np.array_equal(
        np.concatenate((uv1.polarization_array, uv2.polarization_array)),
        uv3.polarization_array,
    )
    assert "Data combined along polarization axis. " in uv3.history


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_add_flag(uvdata_obj):
    uv = uvdata_obj
    uv1 = UVFlag(uv, mode="flag")
    uv2 = uv1.copy()
    uv2.time_array += 1  # Add a day
    uv2.set_lsts_from_time_array()
    uv3 = uv1 + uv2
    assert np.array_equal(
        np.concatenate((uv1.time_array, uv2.time_array)), uv3.time_array
    )
    assert np.array_equal(
        np.concatenate((uv1.baseline_array, uv2.baseline_array)), uv3.baseline_array
    )
    assert np.array_equal(
        np.concatenate((uv1.ant_1_array, uv2.ant_1_array)), uv3.ant_1_array
    )
    assert np.array_equal(
        np.concatenate((uv1.ant_2_array, uv2.ant_2_array)), uv3.ant_2_array
    )
    assert np.array_equal(np.concatenate((uv1.lst_array, uv2.lst_array)), uv3.lst_array)
    assert np.array_equal(
        np.concatenate((uv1.flag_array, uv2.flag_array), axis=0), uv3.flag_array
    )
    assert np.array_equal(uv1.freq_array, uv3.freq_array)
    assert uv3.type == "baseline"
    assert uv3.mode == "flag"
    assert np.array_equal(uv1.polarization_array, uv3.polarization_array)
    assert "Data combined along time axis. " in uv3.history


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_add_errors(uvdata_obj, uvcal_obj):
    uv = uvdata_obj
    uvc = uvcal_obj
    uv1 = UVFlag(uv)
    # Mismatched classes
    with pytest.raises(
        ValueError, match="Only UVFlag objects can be added to a UVFlag object"
    ):
        uv1.__add__(3)

    # Mismatched types
    uv2 = UVFlag(uvc)
    with pytest.raises(ValueError, match="UVFlag object of type "):
        uv1.__add__(uv2)

    # Mismatched modes
    uv3 = UVFlag(uv, mode="flag")
    with pytest.raises(ValueError, match="UVFlag object of mode "):
        uv1.__add__(uv3)

    uv3 = uv1.copy()
    uv3.telescope.name = "foo"
    with pytest.raises(ValueError, match="UVParameter Telescope.name does not match."):
        uv1.__add__(uv3)

    # Invalid axes
    with pytest.raises(ValueError, match="Axis not recognized, must be one of"):
        uv1.__add__(uv1, axis="foo")
    with pytest.raises(ValueError, match="concatenated along antenna axis."):
        uv1.__add__(uv1, axis="antenna")

    with pytest.raises(ValueError, match="concatenated along baseline axis."):
        uv2.__add__(uv2, axis="baseline")

    uv3.telescope.name = uv1.telescope.name
    uv1.freq_array += 1e3
    with pytest.raises(ValueError, match="UVParameter freq_array does not match"):
        uv1.__add__(uv3, axis="baseline")


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_inplace_add():
    uv1a = UVFlag(test_f_file)
    uv1b = uv1a.copy()
    uv2 = uv1a.copy()
    uv2.time_array += 1
    uv2.set_lsts_from_time_array()
    uv1a += uv2
    assert uv1a.__eq__(uv1b + uv2)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_clear_unused_attributes():
    uv = UVFlag(test_f_file)
    assert hasattr(uv, "baseline_array")
    assert hasattr(uv, "ant_1_array")
    assert hasattr(uv, "ant_2_array")
    assert hasattr(uv.telescope, "Nants")
    uv._set_type_antenna()
    uv.clear_unused_attributes()
    # clear_unused_attributes now sets these to None
    assert hasattr(uv, "baseline_array")
    assert uv.baseline_array is None
    assert hasattr(uv, "ant_1_array")
    assert uv.ant_1_array is None
    assert hasattr(uv, "ant_2_array")
    assert uv.ant_2_array is None

    uv._set_mode_flag()
    assert hasattr(uv, "metric_array")
    uv.clear_unused_attributes()
    assert hasattr(uv, "metric_array")
    assert uv.metric_array is None

    # Start over
    uv = UVFlag(test_f_file)
    uv.ant_array = np.array([4])
    uv.flag_array = np.array([5])
    uv.clear_unused_attributes()
    assert hasattr(uv, "ant_array")
    assert uv.ant_array is None
    assert hasattr(uv, "flag_array")
    assert uv.flag_array is None


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_not_equal():
    uvf1 = UVFlag(test_f_file)
    # different class
    assert not uvf1.__eq__(5)
    # different mode
    uvf2 = uvf1.copy()
    uvf2.mode = "flag"
    assert not uvf1.__eq__(uvf2)
    # different type
    uvf2 = uvf1.copy()
    uvf2.type = "antenna"
    assert not uvf1.__eq__(uvf2)
    # array different
    uvf2 = uvf1.copy()
    uvf2.freq_array += 1
    assert not uvf1.__eq__(uvf2)
    # history different
    uvf2 = uvf1.copy()
    uvf2.history += "hello"
    assert not uvf1.__eq__(uvf2, check_history=True)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_waterfall_bl():
    uvf = UVFlag(test_f_file)
    uvf.weights_array = np.ones_like(uvf.weights_array)
    uvf.to_waterfall()
    assert uvf.type == "waterfall"
    assert uvf.metric_array.shape == (
        len(uvf.time_array),
        len(uvf.freq_array),
        len(uvf.polarization_array),
    )
    assert uvf.weights_array.shape == uvf.metric_array.shape


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_waterfall_add_version_str():
    uvf = UVFlag(test_f_file)
    uvf.weights_array = np.ones_like(uvf.weights_array)

    uvf.history = uvf.history.replace(pyuvdata_version_str, "")
    assert pyuvdata_version_str not in uvf.history
    uvf.to_waterfall()
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_waterfall_bl_multi_pol():
    uvf = UVFlag(test_f_file)
    uvf.weights_array = np.ones_like(uvf.weights_array)
    uvf2 = uvf.copy()
    uvf2.polarization_array[0] = -4
    uvf.__add__(uvf2, inplace=True, axis="pol")  # Concatenate to form multi-pol object
    uvf2 = uvf.copy()  # Keep a copy to run with keep_pol=False
    uvf.to_waterfall()
    assert uvf.type == "waterfall"
    assert uvf.metric_array.shape == (
        len(uvf.time_array),
        len(uvf.freq_array),
        len(uvf.polarization_array),
    )
    assert uvf.weights_array.shape == uvf.metric_array.shape
    assert len(uvf.polarization_array) == 2
    # Repeat with keep_pol=False
    uvf2.to_waterfall(keep_pol=False)
    assert uvf2.type == "waterfall"
    assert uvf2.metric_array.shape == (len(uvf2.time_array), len(uvf.freq_array), 1)
    assert uvf2.weights_array.shape == uvf2.metric_array.shape
    assert len(uvf2.polarization_array) == 1
    assert uvf2.polarization_array[0] == np.str_(
        ",".join(map(str, uvf.polarization_array))
    )


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_waterfall_bl_ret_wt_sq():
    uvf = UVFlag(test_f_file)
    Nbls = uvf.Nbls
    uvf.weights_array = 2 * np.ones_like(uvf.weights_array)
    uvf.to_waterfall(return_weights_square=True)
    assert np.all(uvf.weights_square_array == 4 * Nbls)

    # Switch to flag and check that it is now set to None
    uvf.to_flag()
    assert uvf.weights_square_array is None


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_collapse_pol(test_outfile):
    uvf = UVFlag(test_f_file)
    uvf.weights_array = np.ones_like(uvf.weights_array)
    uvf2 = uvf.copy()
    uvf2.polarization_array[0] = -4
    uvf.__add__(uvf2, inplace=True, axis="pol")  # Concatenate to form multi-pol object
    uvf2 = uvf.copy()
    uvf2.collapse_pol()
    assert len(uvf2.polarization_array) == 1
    assert uvf2.polarization_array[0] == np.str_(
        ",".join(map(str, uvf.polarization_array))
    )
    assert uvf2.mode == "metric"
    assert hasattr(uvf2, "metric_array")
    assert hasattr(uvf2, "flag_array")
    assert uvf2.flag_array is None

    # test check passes just to be sure
    uvf2.check()

    # test writing it out and reading in to make sure polarization_array has
    # correct type
    uvf2.write(test_outfile, clobber=True)
    with h5py.File(test_outfile, "r") as h5:
        assert h5["Header/polarization_array"].dtype.type is np.bytes_
    uvf = UVFlag(test_outfile)
    assert uvf._polarization_array.expected_type is str
    assert uvf._polarization_array.acceptable_vals is None
    assert uvf == uvf2
    os.remove(test_outfile)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_collapse_pol_add_pol_axis():
    uvf = UVFlag(test_f_file)
    uvf.weights_array = np.ones_like(uvf.weights_array)
    uvf2 = uvf.copy()
    uvf2.polarization_array[0] = -4
    uvf.__add__(uvf2, inplace=True, axis="pol")  # Concatenate to form multi-pol object
    uvf2 = uvf.copy()
    uvf2.collapse_pol()
    with pytest.raises(NotImplementedError, match="Two UVFlag objects with their"):
        uvf2.__add__(uvf2, axis="pol")


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_collapse_pol_or():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    assert uvf.weights_array is None
    uvf2 = uvf.copy()
    uvf2.polarization_array[0] = -4
    uvf.__add__(uvf2, inplace=True, axis="pol")  # Concatenate to form multi-pol object
    uvf2 = uvf.copy()
    uvf2.collapse_pol(method="or")
    assert len(uvf2.polarization_array) == 1
    assert uvf2.polarization_array[0] == np.str_(
        ",".join(map(str, uvf.polarization_array))
    )
    assert uvf2.mode == "flag"
    assert hasattr(uvf2, "flag_array")
    assert hasattr(uvf2, "metric_array")
    assert uvf2.metric_array is None


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_collapse_pol_add_version_str():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()

    uvf2 = uvf.copy()
    uvf2.polarization_array[0] = -4
    uvf.__add__(uvf2, inplace=True, axis="pol")  # Concatenate to form multi-pol object

    uvf.history = uvf.history.replace(pyuvdata_version_str, "")
    assert pyuvdata_version_str not in uvf.history

    uvf2 = uvf.copy()
    uvf2.collapse_pol(method="or")

    assert pyuvdata_version_str in uvf2.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_collapse_single_pol():
    uvf = UVFlag(test_f_file)
    uvf.weights_array = np.ones_like(uvf.weights_array)
    uvf2 = uvf.copy()
    with check_warnings(UserWarning, "Cannot collapse polarization"):
        uvf.collapse_pol()
    assert uvf == uvf2


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_collapse_pol_flag():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    assert uvf.weights_array is None
    uvf2 = uvf.copy()
    uvf2.polarization_array[0] = -4
    uvf.__add__(uvf2, inplace=True, axis="pol")  # Concatenate to form multi-pol object
    uvf2 = uvf.copy()
    uvf2.collapse_pol()
    assert len(uvf2.polarization_array) == 1
    assert uvf2.polarization_array[0] == np.str_(
        ",".join(map(str, uvf.polarization_array))
    )
    assert uvf2.mode == "metric"
    assert hasattr(uvf2, "metric_array")
    assert hasattr(uvf2, "flag_array")
    assert uvf2.flag_array is None


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_waterfall_bl_flags():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    uvf.to_waterfall()
    assert uvf.type == "waterfall"
    assert uvf.mode == "metric"
    assert uvf.metric_array.shape == (
        len(uvf.time_array),
        len(uvf.freq_array),
        len(uvf.polarization_array),
    )
    assert uvf.weights_array.shape == uvf.metric_array.shape
    assert len(uvf.lst_array) == len(uvf.time_array)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_waterfall_bl_flags_or():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    assert uvf.weights_array is None
    uvf.to_waterfall(method="or")
    assert uvf.type == "waterfall"
    assert uvf.mode == "flag"
    assert uvf.flag_array.shape == (
        len(uvf.time_array),
        len(uvf.freq_array),
        len(uvf.polarization_array),
    )
    assert len(uvf.lst_array) == len(uvf.time_array)
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    uvf.to_waterfall(method="or")
    assert uvf.type == "waterfall"
    assert uvf.mode == "flag"
    assert uvf.flag_array.shape == (
        len(uvf.time_array),
        len(uvf.freq_array),
        len(uvf.polarization_array),
    )
    assert len(uvf.lst_array) == len(uvf.time_array)


def test_to_waterfall_ant(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    uvf.weights_array = np.ones_like(uvf.weights_array)
    uvf.to_waterfall()
    assert uvf.type == "waterfall"
    assert uvf.metric_array.shape == (
        len(uvf.time_array),
        len(uvf.freq_array),
        len(uvf.polarization_array),
    )
    assert uvf.weights_array.shape == uvf.metric_array.shape
    assert len(uvf.lst_array) == len(uvf.time_array)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_waterfall_waterfall():
    uvf = UVFlag(test_f_file)
    uvf.weights_array = np.ones_like(uvf.weights_array)
    uvf.to_waterfall()
    with check_warnings(UserWarning, "This object is already a waterfall"):
        uvf.to_waterfall()


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.parametrize("resort", [True, False])
def test_to_baseline_flags(uvdata_obj, resort):
    uv = uvdata_obj
    uvf = UVFlag(uv)
    uvf.to_waterfall()
    uvf.to_flag()
    uvf.flag_array[0, 10, 0] = True  # Flag time0, chan10
    uvf.flag_array[1, 15, 0] = True  # Flag time1, chan15

    if resort:
        rng = np.random.default_rng()
        new_order = rng.permutation(uvf.telescope.Nants)
        uvf.telescope.reorder_antennas(order=new_order)

    uvf.to_baseline(uv)
    assert uvf.type == "baseline"
    assert np.all(uvf.baseline_array == uv.baseline_array)
    assert np.all(uvf.time_array == uv.time_array)
    times = np.unique(uvf.time_array)
    ntrue = 0.0
    ind = np.where(uvf.time_array == times[0])[0]
    ntrue += len(ind)
    assert np.all(uvf.flag_array[ind, 10, 0])
    ind = np.where(uvf.time_array == times[1])[0]
    ntrue += len(ind)
    assert np.all(uvf.flag_array[ind, 15, 0])
    assert uvf.flag_array.mean() == ntrue / uvf.flag_array.size


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_to_baseline_fill_spws(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv)
    uvf2 = uvf.copy()

    uvf.to_waterfall()
    uvf.Nspws = uvf.spw_array = uvf.flex_spw_id_array = None
    uvf.to_baseline(uv)
    # Assign the weights, since they're mucked by the collapse in the waterfall call
    uvf.weights_array = uvf2.weights_array
    # Also scrub the history, since the two objects are different histories
    uvf.history = uvf2.history

    assert uvf == uvf2


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_to_baseline_metric(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv)
    uvf.to_waterfall()
    # remove telescope info to check that it's set properly
    uvf.telescope.name = None
    uvf.telescope.location = None

    # remove antenna info to check that it's set properly
    uvf.telescope.antenna_names = None
    uvf.telescope.antenna_numbers = None
    uvf.telescope.antenna_positions = None

    uvf.metric_array[0, 10, 0] = 3.2  # Fill in time0, chan10
    uvf.metric_array[1, 15, 0] = 2.1  # Fill in time1, chan15

    uvf.to_baseline(uv)
    assert uvf.telescope.name == uv.telescope.name
    assert np.all(uvf.telescope._location.xyz() == uv.telescope._location.xyz())
    assert np.all(uvf.telescope.antenna_names == uv.telescope.antenna_names)
    assert np.all(uvf.telescope.antenna_numbers == uv.telescope.antenna_numbers)
    assert np.all(uvf.telescope.antenna_positions == uv.telescope.antenna_positions)

    assert np.all(uvf.baseline_array == uv.baseline_array)
    assert np.all(uvf.time_array == uv.time_array)
    times = np.unique(uvf.time_array)
    ind = np.where(uvf.time_array == times[0])[0]
    nt0 = len(ind)
    assert np.all(uvf.metric_array[ind, 10, 0] == 3.2)
    ind = np.where(uvf.time_array == times[1])[0]
    nt1 = len(ind)
    assert np.all(uvf.metric_array[ind, 15, 0] == 2.1)
    assert np.isclose(
        uvf.metric_array.mean(),
        (3.2 * nt0 + 2.1 * nt1) / uvf.metric_array.size,
        rtol=uvf._metric_array.tols[0],
        atol=uvf._metric_array.tols[1],
    )


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_to_baseline_add_version_str(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv)
    uvf.to_waterfall()
    uvf.metric_array[0, 10, 0] = 3.2  # Fill in time0, chan10
    uvf.metric_array[1, 15, 0] = 2.1  # Fill in time1, chan15

    uvf.history = uvf.history.replace(pyuvdata_version_str, "")
    assert pyuvdata_version_str not in uvf.history

    uvf.to_baseline(uv)
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_baseline_to_baseline(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv)
    uvf2 = uvf.copy()
    uvf.to_baseline(uv)
    assert uvf == uvf2


def test_to_baseline_metric_error(uvdata_obj, uvf_from_uvcal):
    uvf = uvf_from_uvcal
    uv = uvdata_obj
    with pytest.raises(
        ValueError,
        match=re.escape(
            "The freq_array on uv is not the same as the freq_array on this object. "
            f"The value on this object is {uvf.freq_array}; the value on uv is "
            f"{uv.freq_array}"
        ),
    ):
        uvf.to_baseline(uv)
    uvf.select(
        polarizations=uvf.polarization_array[0], frequencies=np.squeeze(uv.freq_array)
    )
    with (
        pytest.raises(
            NotImplementedError,
            match="Cannot currently convert from antenna type, metric mode",
        ),
        check_warnings(
            UserWarning,
            match="x_orientation is not the same on this object and on uv. Keeping "
            "the value on this object.",
        ),
    ):
        uvf.to_baseline(uv, force_pol=True)


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_to_baseline_from_antenna(uvdata_obj, uvf_from_uvcal):
    uvf = uvf_from_uvcal
    uv = uvdata_obj

    uvf.select(polarizations=uvf.polarization_array[0], freq_chans=np.arange(uv.Nfreqs))
    uv.freq_array = uvf.freq_array

    with check_warnings(
        UserWarning,
        match=["telescope_location, Nants, antenna_names, antenna_numbers, "] * 2,
    ):
        uvf.set_telescope_params(overwrite=True)
        uv.set_telescope_params(overwrite=True)

    uvf.to_flag()

    ants_data = np.unique(uv.ant_1_array.tolist() + uv.ant_2_array.tolist())
    new_ants = np.setdiff1d(ants_data, uvf.ant_array)

    old_baseline = (uvf.ant_array[0], uvf.ant_array[1])
    old_times = np.unique(uvf.time_array)
    or_flags = np.logical_or(uvf.flag_array[0], uvf.flag_array[1])
    or_flags = np.transpose(or_flags, [1, 0, 2])

    uv2 = uv.copy()
    uvf2 = uvf.copy()

    # hack in the exact times so we can compare some values later
    uv2.select(bls=old_baseline)
    uv2.time_array[: uvf2.time_array.size] = uvf.time_array
    uv2.set_lsts_from_time_array()

    with check_warnings(
        UserWarning,
        match=[
            "feed_array is not the same on this object and on uv.",
            "feed_angle is not the same on this object and on uv.",
        ],
    ):
        uvf.to_baseline(uv, force_pol=True)
    with check_warnings(
        UserWarning,
        match=[
            "feed_array is not the same on this object and on uv.",
            "feed_angle is not the same on this object and on uv.",
        ],
    ):
        uvf2.to_baseline(uv2, force_pol=True)
    uvf.check()

    uvf2.select(bls=old_baseline, times=old_times)
    np.testing.assert_allclose(or_flags, uvf2.flag_array)

    # all new antenna should be completely flagged
    # checks auto correlations
    uvf_new = uvf.select(antenna_nums=new_ants, inplace=False)
    for bl in np.unique(uvf_new.baseline_array):
        uvf2 = uvf_new.select(bls=uv.baseline_to_antnums(bl), inplace=False)
        assert np.all(uvf2.flag_array)

    # check for baselines with one new antenna
    bls = [
        uvf.baseline_to_antnums(bl)
        for bl in uvf.baseline_array
        if np.intersect1d(new_ants, uvf.baseline_to_antnums(bl)).size > 0
    ]
    uvf_new = uvf.select(bls=bls, inplace=False)
    for bl in np.unique(uvf_new.baseline_array):
        uvf2 = uvf_new.select(bls=uv.baseline_to_antnums(bl), inplace=False)
        assert np.all(uvf2.flag_array)


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
@pytest.mark.parametrize("method", ["to_antenna", "to_baseline"])
def test_to_baseline_antenna_errors(uvdata_obj, uvcal_obj, method):
    if method == "to_baseline":
        uv = uvdata_obj
        msg = "Must pass in UVData object or UVFlag object"
    else:
        uv = uvcal_obj
        msg = "Must pass in UVCal object or UVFlag object"

        uvf = UVFlag(uvdata_obj)
        with pytest.raises(
            ValueError, match='Cannot convert from type "baseline" to "antenna".'
        ):
            uvf.to_antenna(uv)

    uvf = UVFlag(test_f_file)

    uvf.to_waterfall()
    with pytest.raises(ValueError, match=msg):
        getattr(uvf, method)(7.3)  # invalid matching object

    if method == "to_antenna":
        with pytest.raises(
            ValueError,
            match=re.escape(
                "The freq_array on uv is not the same as the freq_array on this "
                f"object. The value on this object is {uvf.freq_array}; the value "
                f"on uv is {uv.freq_array}"
            ),
        ):
            getattr(uvf, method)(uv)
        uv.select(frequencies=np.squeeze(uvf.freq_array))

    uvf2 = uvf.copy()
    uvf2.channel_width = uvf2.channel_width / 2.0
    with pytest.raises(
        ValueError, match="channel_width is not the same on this object and on uv"
    ):
        getattr(uvf2, method)(uv)

    uvf2 = uvf.copy()
    uvf2.Nspws = 2
    uvf2.spw_array = np.array([0, 1])
    uvf2.check()
    with pytest.raises(
        ValueError, match="spw_array is not the same on this object and on uv"
    ):
        getattr(uvf2, method)(uv)
    uv2 = uv.copy()
    uv2.Nspws = 2
    uv2.spw_array = np.array([0, 1])
    uv2.check()
    uvf2.flex_spw_id_array = np.zeros(uv.Nfreqs, dtype=int)
    uvf2.flex_spw_id_array[: uv.Nfreqs // 2] = 1
    uvf2.check()
    with pytest.raises(
        ValueError, match="flex_spw_id_array is not the same on this object and on uv"
    ):
        getattr(uvf2, method)(uv2)

    uvf2 = uvf.copy()
    uvf2.polarization_array[0] = -4
    with pytest.raises(ValueError, match="Polarizations do not match."):
        getattr(uvf2, method)(uv)
    uvf.__iadd__(uvf2, axis="polarization")

    with pytest.raises(ValueError, match="Polarizations could not be made to match."):
        getattr(uvf, method)(uv)  # Mismatched pols, can't be forced


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_to_baseline_force_pol(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv)
    uvf.to_waterfall()
    uvf.to_flag()
    uvf.flag_array[0, 10, 0] = True  # Flag time0, chan10
    uvf.flag_array[1, 15, 0] = True  # Flag time1, chan15
    uvf.polarization_array[0] = -4  # Change pol, but force pol anyway
    uvf.to_baseline(uv, force_pol=True)
    assert np.all(uvf.baseline_array == uv.baseline_array)
    assert np.all(uvf.time_array == uv.time_array)
    assert np.array_equal(uvf.polarization_array, uv.polarization_array)
    times = np.unique(uvf.time_array)
    ntrue = 0.0
    ind = np.where(uvf.time_array == times[0])[0]
    ntrue += len(ind)
    assert np.all(uvf.flag_array[ind, 10, 0])
    ind = np.where(uvf.time_array == times[1])[0]
    ntrue += len(ind)
    assert np.all(uvf.flag_array[ind, 15, 0])
    assert uvf.flag_array.mean() == ntrue / uvf.flag_array.size


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_to_baseline_force_pol_npol_gt_1(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv)
    uvf.to_waterfall()
    uvf.to_flag()
    uvf.flag_array[0, 10, 0] = True  # Flag time0, chan10
    uvf.flag_array[1, 15, 0] = True  # Flag time1, chan15

    uv2 = uv.copy()
    uv2.polarization_array[0] = -6
    uv += uv2
    uvf.to_baseline(uv, force_pol=True)
    assert np.all(uvf.baseline_array == uv.baseline_array)
    assert np.all(uvf.time_array == uv.time_array)
    assert np.array_equal(uvf.polarization_array, uv.polarization_array)
    assert uvf.Npols == len(uvf.polarization_array)


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_to_baseline_metric_force_pol(uvdata_obj):
    uv = uvdata_obj
    uvf = UVFlag(uv)
    uvf.to_waterfall()
    uvf.metric_array[0, 10, 0] = 3.2  # Fill in time0, chan10
    uvf.metric_array[1, 15, 0] = 2.1  # Fill in time1, chan15
    uvf.polarization_array[0] = -4
    uvf.to_baseline(uv, force_pol=True)
    assert np.all(uvf.baseline_array == uv.baseline_array)
    assert np.all(uvf.time_array == uv.time_array)
    assert np.array_equal(uvf.polarization_array, uv.polarization_array)
    times = np.unique(uvf.time_array)
    ind = np.where(uvf.time_array == times[0])[0]
    nt0 = len(ind)
    assert np.all(uvf.metric_array[ind, 10, 0] == 3.2)
    ind = np.where(uvf.time_array == times[1])[0]
    nt1 = len(ind)
    assert np.all(uvf.metric_array[ind, 15, 0] == 2.1)
    assert np.isclose(
        uvf.metric_array.mean(),
        (3.2 * nt0 + 2.1 * nt1) / uvf.metric_array.size,
        rtol=uvf._metric_array.tols[0],
        atol=uvf._metric_array.tols[1],
    )


@pytest.mark.parametrize("resort", [True, False])
def test_to_antenna_flags(uvcal_obj, resort):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    uvf.freq_array = uvc.freq_array

    uvf.to_waterfall()
    uvf.to_flag()
    uvf.flag_array[0, 10, 0] = True  # Flag time0, chan10
    uvf.flag_array[1, 15, 0] = True  # Flag time1, chan15

    if resort:
        rng = np.random.default_rng()
        new_order = rng.permutation(uvf.telescope.Nants)
        uvf.telescope.antenna_numbers = uvf.telescope.antenna_numbers[new_order]
        uvf.telescope.antenna_names = uvf.telescope.antenna_names[new_order]
        uvf.telescope.antenna_positions = uvf.telescope.antenna_positions[new_order, :]

    uvf.to_antenna(uvc)
    assert uvf.type == "antenna"
    assert np.all(uvf.ant_array == uvc.ant_array)
    assert np.all(uvf.time_array == uvc.time_array)
    assert np.all(uvf.flag_array[:, 10, 0, 0])
    assert np.all(uvf.flag_array[:, 15, 1, 0])
    assert uvf.flag_array.mean() == 2.0 * uvc.Nants_data / uvf.flag_array.size


def test_to_antenna_add_version_str(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    uvf.to_waterfall()
    uvf.to_flag()
    uvf.flag_array[0, 10, 0] = True  # Flag time0, chan10
    uvf.flag_array[1, 15, 0] = True  # Flag time1, chan15
    uvf.history = uvf.history.replace(pyuvdata_version_str, "")
    assert pyuvdata_version_str not in uvf.history

    # also change the instrument name to check warning
    uvf.telescope.instrument = uvf.telescope.name

    with check_warnings(
        UserWarning,
        match="instrument is not the same on this object and on uv. Keeping the "
        "value on this object.",
    ):
        uvf.to_antenna(uvc)
    assert pyuvdata_version_str in uvf.history


def test_to_antenna_metric(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    uvf.to_waterfall()
    # remove telescope info to check that it's set properly
    uvf.telescope.name = None
    uvf.telescope.location = None

    # remove antenna info to check that it's set properly
    uvf.telescope.antenna_names = None
    uvf.telescope.antenna_numbers = None
    uvf.telescope.antenna_positions = None

    uvf.metric_array[0, 10, 0] = 3.2  # Fill in time0, chan10
    uvf.metric_array[1, 15, 0] = 2.1  # Fill in time1, chan15
    uvf.to_antenna(uvc)
    assert uvf.telescope.name == uvc.telescope.name
    assert np.all(uvf.telescope._location.xyz() == uvc.telescope._location.xyz())
    assert np.all(uvf.telescope.antenna_names == uvc.telescope.antenna_names)
    assert np.all(uvf.telescope.antenna_numbers == uvc.telescope.antenna_numbers)
    assert np.all(uvf.telescope.antenna_positions == uvc.telescope.antenna_positions)

    assert np.all(uvf.ant_array == uvc.ant_array)
    assert np.all(uvf.time_array == uvc.time_array)
    assert np.all(uvf.metric_array[:, 10, 0, 0] == 3.2)
    assert np.all(uvf.metric_array[:, 15, 1, 0] == 2.1)
    assert np.isclose(
        uvf.metric_array.mean(),
        (3.2 + 2.1) * uvc.Nants_data / uvf.metric_array.size,
        rtol=uvf._metric_array.tols[0],
        atol=uvf._metric_array.tols[1],
    )


def test_to_antenna_flags_match_uvflag(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    uvf2 = uvf.copy()
    uvf.to_waterfall()
    uvf.to_flag()
    uvf.flag_array[0, 10, 0] = True  # Flag time0, chan10
    uvf.flag_array[1, 15, 0] = True  # Flag time1, chan15
    uvf.to_antenna(uvf2)
    assert np.all(uvf.ant_array == uvc.ant_array)
    assert np.all(uvf.time_array == uvc.time_array)
    assert np.all(uvf.flag_array[:, 10, 0, 0])
    assert np.all(uvf.flag_array[:, 15, 1, 0])
    assert uvf.flag_array.mean() == 2.0 * uvc.Nants_data / uvf.flag_array.size


def test_antenna_to_antenna(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    uvf2 = uvf.copy()
    uvf.to_antenna(uvc)
    assert uvf == uvf2


def test_to_antenna_force_pol(uvcal_obj):
    uvc = uvcal_obj
    uvc.select(jones=-5)
    uvf = UVFlag(uvc)
    uvf.to_waterfall()
    uvf.to_flag()
    uvf.flag_array[0, 10, 0] = True  # Flag time0, chan10
    uvf.flag_array[1, 15, 0] = True  # Flag time1, chan15
    uvf.polarization_array[0] = -4  # Change pol, but force pol anyway
    uvf.to_antenna(uvc, force_pol=True)
    assert np.all(uvf.ant_array == uvc.ant_array)
    assert np.all(uvf.time_array == uvc.time_array)
    assert np.array_equal(uvf.polarization_array, uvc.jones_array)
    assert np.all(uvf.flag_array[:, 10, 0, 0])
    assert np.all(uvf.flag_array[:, 15, 1, 0])
    assert uvf.flag_array.mean() == 2 * uvc.Nants_data / uvf.flag_array.size


def test_to_antenna_metric_force_pol(uvcal_obj):
    uvc = uvcal_obj
    uvc.select(jones=-5)
    uvf = UVFlag(uvc)
    uvf.to_waterfall()
    uvf.metric_array[0, 10, 0] = 3.2  # Fill in time0, chan10
    uvf.metric_array[1, 15, 0] = 2.1  # Fill in time1, chan15
    uvf.polarization_array[0] = -4
    uvf.to_antenna(uvc, force_pol=True)
    assert np.all(uvf.ant_array == uvc.ant_array)
    assert np.all(uvf.time_array == uvc.time_array)
    assert np.array_equal(uvf.polarization_array, uvc.jones_array)
    assert np.all(uvf.metric_array[:, 10, 0, 0] == 3.2)
    assert np.all(uvf.metric_array[:, 15, 1, 0] == 2.1)
    assert np.isclose(
        uvf.metric_array.mean(),
        (3.2 + 2.1) * uvc.Nants_data / uvf.metric_array.size,
        rtol=uvf._metric_array.tols[0],
        atol=uvf._metric_array.tols[1],
    )


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_copy():
    uvf = UVFlag(test_f_file)
    uvf2 = uvf.copy()
    assert uvf == uvf2
    # Make sure it's a copy and not just pointing to same object
    uvf.to_waterfall()
    assert uvf != uvf2


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_or():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    uvf2 = uvf.copy()
    uvf2.flag_array = np.ones_like(uvf2.flag_array)
    uvf.flag_array[0] = True
    uvf2.flag_array[0] = False
    uvf2.flag_array[1] = False
    uvf3 = uvf | uvf2
    assert np.all(uvf3.flag_array[0])
    assert not np.any(uvf3.flag_array[1])
    assert np.all(uvf3.flag_array[2:])


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_or_add_version_str():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    uvf.history = uvf.history.replace(pyuvdata_version_str, "")

    assert pyuvdata_version_str not in uvf.history
    uvf2 = uvf.copy()
    uvf2.flag_array = np.ones_like(uvf2.flag_array)
    uvf.flag_array[0] = True
    uvf2.flag_array[0] = False
    uvf2.flag_array[1] = False
    uvf3 = uvf | uvf2

    assert pyuvdata_version_str in uvf3.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_or_error():
    uvf = UVFlag(test_f_file)
    uvf2 = uvf.copy()
    uvf.to_flag()
    with pytest.raises(ValueError, match='UVFlag object must be in "flag" mode'):
        uvf.__or__(uvf2)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_or_add_history():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    uvf2 = uvf.copy()
    uvf2.history = "Different history"
    uvf3 = uvf | uvf2
    assert uvf.history in uvf3.history
    assert uvf2.history in uvf3.history
    assert "Flags OR'd with:" in uvf3.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_ior():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    uvf2 = uvf.copy()
    uvf2.flag_array = np.ones_like(uvf2.flag_array)
    uvf.flag_array[0] = True
    uvf2.flag_array[0] = False
    uvf2.flag_array[1] = False
    uvf |= uvf2
    assert np.all(uvf.flag_array[0])
    assert not np.any(uvf.flag_array[1])
    assert np.all(uvf.flag_array[2:])


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_flag():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    assert hasattr(uvf, "flag_array")
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None
    assert uvf.mode == "flag"
    assert 'Converted to mode "flag"' in uvf.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_flag_add_version_str():
    uvf = UVFlag(test_f_file)
    uvf.history = uvf.history.replace(pyuvdata_version_str, "")
    assert pyuvdata_version_str not in uvf.history

    uvf.to_flag()
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_flag_threshold():
    uvf = UVFlag(test_f_file)
    uvf.metric_array = np.zeros_like(uvf.metric_array)
    uvf.metric_array[0, 4, 0] = 2.0
    uvf.to_flag(threshold=1.0)
    assert hasattr(uvf, "flag_array")
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None
    assert uvf.mode == "flag"
    assert uvf.flag_array[0, 4, 0]
    assert np.sum(uvf.flag_array) == 1.0
    assert 'Converted to mode "flag"' in uvf.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_flag_to_flag():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    uvf2 = uvf.copy()
    uvf2.to_flag()
    assert uvf == uvf2


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_flag_unknown_mode():
    uvf = UVFlag(test_f_file)
    uvf.mode = "foo"
    with pytest.raises(ValueError, match="Unknown UVFlag mode: foo"):
        uvf.to_flag()


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_metric_baseline():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    uvf.flag_array[:, 10] = True
    uvf.flag_array[1, :] = True
    assert hasattr(uvf, "flag_array")
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None
    assert uvf.mode == "flag"
    uvf.to_metric(convert_wgts=True)
    assert hasattr(uvf, "metric_array")
    assert hasattr(uvf, "flag_array")
    assert uvf.flag_array is None
    assert uvf.mode == "metric"
    assert 'Converted to mode "metric"' in uvf.history
    np.testing.assert_allclose(
        uvf.weights_array[1],
        0.0,
        rtol=uvf._weights_array.tols[0],
        atol=uvf._weights_array.tols[1],
    )
    np.testing.assert_allclose(
        uvf.weights_array[:, 10],
        0.0,
        rtol=uvf._weights_array.tols[0],
        atol=uvf._weights_array.tols[1],
    )


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_metric_add_version_str():
    uvf = UVFlag(test_f_file)
    uvf.to_flag()
    uvf.flag_array[:, 10] = True
    uvf.flag_array[1, :] = True
    assert hasattr(uvf, "flag_array")
    assert hasattr(uvf, "metric_array")
    assert uvf.metric_array is None
    assert uvf.mode == "flag"

    uvf.history = uvf.history.replace(pyuvdata_version_str, "")
    assert pyuvdata_version_str not in uvf.history

    uvf.to_metric(convert_wgts=True)
    assert pyuvdata_version_str in uvf.history


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_metric_waterfall():
    uvf = UVFlag(test_f_file)
    uvf.to_waterfall()
    uvf.to_flag()
    uvf.flag_array[:, 10] = True
    uvf.flag_array[1, :, :] = True
    uvf.to_metric(convert_wgts=True)
    np.testing.assert_allclose(
        uvf.weights_array[1],
        0.0,
        rtol=uvf._weights_array.tols[0],
        atol=uvf._weights_array.tols[1],
    )
    np.testing.assert_allclose(
        uvf.weights_array[:, 10],
        0.0,
        rtol=uvf._weights_array.tols[0],
        atol=uvf._weights_array.tols[1],
    )


def test_to_metric_antenna(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc, mode="flag")
    uvf.flag_array[10, :, 1, :] = True
    uvf.flag_array[15, 3, :, :] = True
    uvf.to_metric(convert_wgts=True)
    np.testing.assert_allclose(
        uvf.weights_array[10, :, 1, :],
        0.0,
        rtol=uvf._weights_array.tols[0],
        atol=uvf._weights_array.tols[1],
    )
    np.testing.assert_allclose(
        uvf.weights_array[15, 3, :, :],
        0.0,
        rtol=uvf._weights_array.tols[0],
        atol=uvf._weights_array.tols[1],
    )


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_metric_to_metric():
    uvf = UVFlag(test_f_file)
    uvf2 = uvf.copy()
    uvf.to_metric()
    assert uvf == uvf2


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_to_metric_unknown_mode():
    uvf = UVFlag(test_f_file)
    uvf.mode = "foo"
    with pytest.raises(ValueError, match="Unknown UVFlag mode: foo"):
        uvf.to_metric()


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_antpair2ind():
    uvf = UVFlag(test_f_file)
    ind = uvf.antpair2ind(uvf.ant_1_array[0], uvf.ant_2_array[0])
    assert np.all(uvf.ant_1_array[ind] == uvf.ant_1_array[0])
    assert np.all(uvf.ant_2_array[ind] == uvf.ant_2_array[0])


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_antpair2ind_nonbaseline():
    uvf = UVFlag(test_f_file)
    uvf.to_waterfall()
    with pytest.raises(
        ValueError,
        match=f"UVFlag object of type {uvf.type} does not contain antenna pairs "
        "to index.",
    ):
        uvf.antpair2ind(0, 3)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_baseline_to_antnums():
    uvf = UVFlag(test_f_file)
    a1, a2 = uvf.baseline_to_antnums(uvf.baseline_array[0])
    assert a1 == uvf.ant_1_array[0]
    assert a2 == uvf.ant_2_array[0]


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_get_baseline_nums():
    uvf = UVFlag(test_f_file)
    bls = uvf.get_baseline_nums()
    assert np.array_equal(bls, np.unique(uvf.baseline_array))


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_get_pols():
    uvf = UVFlag(test_f_file)
    pols = uvf.get_pols()
    pols2 = utils.polnum2str(
        uvf.polarization_array,
        x_orientation=uvf.telescope.get_x_orientation_from_feeds(),
    )
    assert np.array_equal(pols, pols2)


@pytest.mark.filterwarnings("ignore:The lst_array is not self-consistent")
def test_get_antpairs():
    uvf = UVFlag(test_f_file)
    antpairs = uvf.get_antpairs()
    for a1, a2 in antpairs:
        ind = np.where((uvf.ant_1_array == a1) & (uvf.ant_2_array == a2))[0]
        assert len(ind) > 0
    for a1, a2 in zip(uvf.ant_1_array, uvf.ant_2_array, strict=True):
        assert (a1, a2) in antpairs


def test_combine_metrics_inplace(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    np.random.seed(44)
    uvf.metric_array = np.random.normal(size=uvf.metric_array.shape)
    uvf2 = uvf.copy()
    uvf2.metric_array *= 2
    uvf3 = uvf.copy()
    uvf3.metric_array *= 3
    uvf.combine_metrics([uvf2, uvf3])
    factor = np.sqrt((1 + 4 + 9) / 3.0) / 2.0
    np.testing.assert_allclose(
        uvf.metric_array,
        np.abs(uvf2.metric_array) * factor,
        rtol=uvf._metric_array.tols[0],
        atol=uvf._metric_array.tols[1],
    )


def test_combine_metrics_not_inplace(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    np.random.seed(44)
    uvf.metric_array = np.random.normal(size=uvf.metric_array.shape)
    uvf2 = uvf.copy()
    uvf2.metric_array *= 2
    uvf3 = uvf.copy()
    uvf3.metric_array *= 3
    uvf4 = uvf.combine_metrics([uvf2, uvf3], inplace=False)
    factor = np.sqrt((1 + 4 + 9) / 3.0)
    np.testing.assert_allclose(
        uvf4.metric_array,
        np.abs(uvf.metric_array) * factor,
        rtol=uvf._metric_array.tols[0],
        atol=uvf._metric_array.tols[1],
    )


def test_combine_metrics_not_uvflag(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    with pytest.raises(
        ValueError, match='"others" must be UVFlag or list of UVFlag objects'
    ):
        uvf.combine_metrics("bubblegum")


def test_combine_metrics_not_metric(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    np.random.seed(44)
    uvf.metric_array = np.random.normal(size=uvf.metric_array.shape)
    uvf2 = uvf.copy()
    uvf2.to_flag()
    with pytest.raises(
        ValueError, match='UVFlag object and "others" must be in "metric"'
    ):
        uvf.combine_metrics(uvf2)


def test_combine_metrics_wrong_shape(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    np.random.seed(44)
    uvf.metric_array = np.random.normal(size=uvf.metric_array.shape)
    uvf2 = uvf.copy()
    uvf2.to_waterfall()
    with pytest.raises(ValueError, match="UVFlag metric array shapes do not match."):
        uvf.combine_metrics(uvf2)


def test_combine_metrics_add_version_str(uvcal_obj):
    uvc = uvcal_obj
    uvf = UVFlag(uvc)
    uvf.history = uvf.history.replace(pyuvdata_version_str, "")

    assert pyuvdata_version_str not in uvf.history
    np.random.seed(44)
    uvf.metric_array = np.random.normal(size=uvf.metric_array.shape)
    uvf2 = uvf.copy()
    uvf2.metric_array *= 2
    uvf3 = uvf.copy()
    uvf3.metric_array *= 3
    uvf4 = uvf.combine_metrics([uvf2, uvf3], inplace=False)

    assert pyuvdata_version_str in uvf4.history


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_super(uvdata_obj):
    class TestClass(UVFlag):
        def __init__(
            self,
            indata,
            mode="metric",
            copy_flags=False,
            waterfall=False,
            history="",
            label="",
            test_property="prop",
        ):
            super().__init__(
                indata,
                mode=mode,
                copy_flags=copy_flags,
                waterfall=waterfall,
                history=history,
                label=label,
            )

            self.test_property = test_property

    uv = uvdata_obj

    tc = TestClass(uv, test_property="test_property")

    # UVFlag.__init__ is tested, so just see if it has a metric array
    assert hasattr(tc, "metric_array")
    # Check that it has the property
    assert tc.test_property == "test_property"


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_flags2waterfall_uvdata(uvdata_obj):
    uv = uvdata_obj

    np.random.seed(0)
    uv.flag_array = np.random.randint(0, 2, size=uv.flag_array.shape, dtype=bool)
    wf = flags2waterfall(uv)
    np.testing.assert_allclose(np.mean(wf), np.mean(uv.flag_array))
    assert wf.shape == (uv.Ntimes, uv.Nfreqs)

    wf = flags2waterfall(uv, keep_pol=True)
    assert wf.shape == (uv.Ntimes, uv.Nfreqs, uv.Npols)

    # Test external flag_array
    uv.flag_array = np.zeros_like(uv.flag_array)
    f = np.random.randint(0, 2, size=uv.flag_array.shape, dtype=bool)
    wf = flags2waterfall(uv, flag_array=f)
    np.testing.assert_allclose(np.mean(wf), np.mean(f))
    assert wf.shape == (uv.Ntimes, uv.Nfreqs)


def test_flags2waterfall_uvcal(uvcal_obj):
    uvc = uvcal_obj

    uvc.flag_array = np.random.randint(0, 2, size=uvc.flag_array.shape, dtype=bool)
    wf = flags2waterfall(uvc)
    np.testing.assert_allclose(np.mean(wf), np.mean(uvc.flag_array))
    assert wf.shape == (uvc.Ntimes, uvc.Nfreqs)

    wf = flags2waterfall(uvc, keep_pol=True)
    assert wf.shape == (uvc.Ntimes, uvc.Nfreqs, uvc.Njones)


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_flags2waterfall_errors(uvdata_obj):
    # First argument must be UVData or UVCal object
    with pytest.raises(
        ValueError,
        match=re.escape(
            "flags2waterfall() requires a UVData or UVCal object as the first argument."
        ),
    ):
        flags2waterfall(5)

    uv = uvdata_obj
    # Flag array must have same shape as uv.flag_array
    with pytest.raises(ValueError, match="Flag array must align with UVData or UVCal"):
        flags2waterfall(uv, flag_array=np.array([4, 5]))


def test_and_rows_cols():
    d = np.zeros((10, 20), np.bool_)
    d[1, :] = True
    d[:, 2] = True
    d[5, 10:20] = True
    d[5:8, 5] = True

    o = and_rows_cols(d)
    assert o[1, :].all()
    assert o[:, 2].all()
    assert not o[5, :].all()
    assert not o[:, 5].all()


def test_select_waterfall_errors(uvf_from_waterfall):
    uvf = uvf_from_waterfall
    with pytest.raises(
        ValueError, match="Cannot select on antenna_nums with waterfall"
    ):
        uvf.select(antenna_nums=[0, 1, 2])

    with pytest.raises(ValueError, match="Cannot select on bls with waterfall"):
        uvf.select(bls=[(0, 1), (0, 2)])


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
@pytest.mark.parametrize("invert", [True, False])
@pytest.mark.parametrize("dimension", list(range(1, 4)))
def test_select_blt_inds(uvf_from_data, uvf_mode, dimension, invert):
    uvf = uvf_from_data

    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    np.random.seed(0)
    n_select = uvf.Nblts

    blt_inds = np.random.choice(n_select, size=n_select // 2, replace=False)
    blt_discard = np.nonzero(np.isin(np.arange(n_select), blt_inds, invert=True))
    new_nblts = n_select // 2

    if dimension == 1:
        blt_inds = np.atleast_1d(blt_inds)
        blt_discard = np.atleast_1d(blt_discard)
    elif dimension == 2:
        blt_inds = np.atleast_2d(blt_inds)
        blt_discard = np.atleast_2d(blt_discard)
    elif dimension == 3:
        blt_inds = np.atleast_3d(blt_inds)
        blt_discard = np.atleast_3d(blt_discard)

    uvf1 = uvf.select(
        blt_inds=blt_discard if invert else blt_inds, inplace=False, invert=invert
    )

    # test the data was extracted correctly for each case
    for param_name, new_param in zip(
        uvf._data_params, uvf1.data_like_parameters, strict=True
    ):
        old_param = getattr(uvf, param_name)
        old_param_obj = getattr(uvf, "_" + param_name)
        blt_inds_use = np.atleast_1d(blt_inds.squeeze())
        np.testing.assert_allclose(
            old_param[blt_inds_use],
            new_param,
            rtol=old_param_obj.tols[0],
            atol=old_param_obj.tols[1],
        )

    assert uvf1.Nblts == new_nblts

    # verify that histories are different
    assert not utils.history._check_histories(uvf.history, uvf1.history)

    assert utils.history._check_histories(
        uvf.history + "  Downselected to specific baseline-times using pyuvdata.",
        uvf1.history,
    )


@cases_decorator
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
@pytest.mark.parametrize(
    "select_kwargs,err_msg",
    [
        ({"blt_inds": []}, "No baseline-times were found"),
        ({"blt_inds": [int(1e9)]}, "blt_inds contains indices that are too large"),
        ({"blt_inds": [-1]}, "blt_inds contains indices that are negative"),
    ],
)
def test_select_blt_inds_errors(input_uvf, uvf_mode, select_kwargs, err_msg):
    uvf = input_uvf

    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()

    if uvf.type != "baseline":
        err_msg = 'Only "baseline" mode UVFlag objects may select along the blt axis'

    with pytest.raises(ValueError, match=err_msg):
        uvf.select(strict=True, **select_kwargs)


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@cases_decorator_no_waterfall
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
@pytest.mark.parametrize("invert", [True, False])
@pytest.mark.parametrize("dimension", list(range(1, 4)))
def test_select_antenna_nums(input_uvf, uvf_mode, dimension, invert):
    uvf = input_uvf

    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()

    old_history = copy.deepcopy(uvf.history)
    np.random.seed(0)
    if uvf.type == "baseline":
        unique_ants = np.unique(uvf.ant_1_array.tolist() + uvf.ant_2_array.tolist())
        ants_to_keep = np.random.choice(
            unique_ants, size=unique_ants.size // 2, replace=False
        )

        blts_select = [
            (a1 in ants_to_keep) & (a2 in ants_to_keep)
            for (a1, a2) in zip(uvf.ant_1_array, uvf.ant_2_array, strict=True)
        ]
        Nblts_selected = np.sum(blts_select)
    else:
        unique_ants = np.unique(uvf.ant_array)
        ants_to_keep = np.random.choice(
            unique_ants, size=unique_ants.size // 2, replace=False
        )
    ants_to_discard = unique_ants[np.isin(unique_ants, ants_to_keep, invert=True)]

    if dimension == 1:
        ants_to_keep = np.atleast_1d(ants_to_keep)
        ants_to_discard = np.atleast_1d(ants_to_discard)
    elif dimension == 2:
        ants_to_keep = np.atleast_2d(ants_to_keep)
        ants_to_discard = np.atleast_2d(ants_to_discard)
    elif dimension == 3:
        ants_to_keep = np.atleast_3d(ants_to_keep)
        ants_to_discard = np.atleast_3d(ants_to_discard)

    uvf2 = uvf.copy()
    uvf2.select(antenna_nums=ants_to_discard if invert else ants_to_keep, invert=invert)
    # make 1-D for the remaining iterators in tests
    ants_to_keep = ants_to_keep.squeeze()

    assert ants_to_keep.size == uvf2.Nants_data
    if uvf2.type == "baseline":
        assert Nblts_selected == uvf2.Nblts
        for ant in ants_to_keep:
            assert ant in uvf2.ant_1_array or ant in uvf2.ant_2_array
        for ant in np.unique(uvf2.ant_1_array.tolist() + uvf2.ant_2_array.tolist()):
            assert ant in ants_to_keep
    else:
        for ant in ants_to_keep:
            assert ant in uvf2.ant_array
        for ant in np.unique(uvf2.ant_array):
            assert ant in ants_to_keep

    assert utils.history._check_histories(
        old_history + "  Downselected to specific antennas using pyuvdata.",
        uvf2.history,
    )


@cases_decorator_no_waterfall
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
def test_select_antenna_nums_error(input_uvf, uvf_mode):
    uvf = input_uvf
    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    # also test for error if antenna numbers not present in data
    with pytest.raises(
        ValueError, match=re.escape("Antenna number [708] is not present")
    ):
        uvf.select(antenna_nums=[708, 9, 10], strict=True)

    if uvf.type == "antenna":
        msg = "No data matching this antenna selection exists."
    else:
        msg = "No baseline-times were found that match criteria"

    with pytest.raises(ValueError, match=msg):
        uvf.select(antenna_nums=708, strict=None)


def sort_bl(p):
    """Sort a tuple that starts with a pair of antennas, and may have stuff after."""
    if p[1] >= p[0]:
        return p
    return (p[1], p[0]) + p[2:]


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@cases_decorator_no_waterfall
@pytest.mark.parametrize("invert", [True, False])
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
@pytest.mark.parametrize("do_pol", [True, False])
def test_select_bls(input_uvf, uvf_mode, invert, do_pol):
    uvf = input_uvf
    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    np.random.seed(0)

    if uvf.type != "baseline":
        with pytest.raises(
            ValueError,
            match='Only "baseline" mode UVFlag objects may select along the '
            "baseline axis",
        ):
            uvf.select(bls=[(0, 1)])
    elif invert and do_pol:
        with pytest.raises(
            ValueError, match="Cannot provide length-3 tuples and also set invert=True."
        ):
            uvf.select(bls=[(0, 1, "xx")], invert=invert)
    else:
        old_history = copy.deepcopy(uvf.history)
        bls_select = np.random.choice(
            uvf.baseline_array, size=uvf.Nbls // 2, replace=False
        )
        first_ants, second_ants = uvf.baseline_to_antnums(bls_select)

        # give the conjugate bls for a few baselines
        first_ants[5:8], second_ants[5:8] = (
            copy.copy(second_ants[5:8]),
            copy.copy(first_ants[5:8]),
        )

        new_unique_ants = np.unique(first_ants.tolist() + second_ants.tolist())
        if do_pol:
            ant_pairs_to_keep = list(
                zip(first_ants, second_ants, ["xx"] * len(first_ants), strict=True)
            )
        else:
            ant_pairs_to_keep = list(zip(first_ants, second_ants, strict=True))
        sorted_pairs_to_keep = [sort_bl(p) for p in ant_pairs_to_keep]

        blts_select = [
            sort_bl((a1, a2, "xx") if do_pol else (a1, a2)) in sorted_pairs_to_keep
            for (a1, a2) in zip(uvf.ant_1_array, uvf.ant_2_array, strict=True)
        ]
        Nblts_selected = np.sum(blts_select)

        if invert:
            bls_discard = uvf.baseline_array[
                np.isin(uvf.baseline_array, bls_select, invert=True)
            ]
            first_ants, second_ants = uvf.baseline_to_antnums(bls_discard)

            # give the conjugate bls for a few baselines
            first_ants[5:8], second_ants[5:8] = (
                copy.copy(second_ants[5:8]),
                copy.copy(first_ants[5:8]),
            )
            ant_pairs_to_discard = list(zip(first_ants, second_ants, strict=True))

        uvf2 = uvf.copy()
        uvf2.select(
            bls=ant_pairs_to_discard if invert else ant_pairs_to_keep, invert=invert
        )

        sorted_pairs_object2 = [
            sort_bl(p) + (("xx",) if do_pol else ())
            for p in zip(uvf2.ant_1_array, uvf2.ant_2_array, strict=True)
        ]

        assert len(new_unique_ants) == uvf2.Nants_data
        assert Nblts_selected == uvf2.Nblts
        for ant in new_unique_ants:
            assert ant in uvf2.ant_1_array or ant in uvf2.ant_2_array
        for ant in np.unique(uvf2.ant_1_array.tolist() + uvf2.ant_2_array.tolist()):
            assert ant in new_unique_ants
        for pair in sorted_pairs_to_keep:
            assert pair in sorted_pairs_object2
        for pair in sorted_pairs_object2:
            assert pair in sorted_pairs_to_keep

        if do_pol:
            msg = (
                "  Downselected to specific antenna pairs, "
                "polarizations using pyuvdata."
            )
        else:
            msg = "  Downselected to specific antenna pairs using pyuvdata."

        assert utils.history._check_histories(old_history + msg, uvf2.history)


@cases_decorator_no_waterfall
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
def test_select_single_bls(input_uvf, uvf_mode):
    uvf = input_uvf
    # check that you can specify a single pair without errors
    if uvf.type == "baseline":
        getattr(uvf, uvf_mode)()
        uvf.select(bls=(9, 10, "xx"))
        sorted_pairs_object2 = [
            sort_bl(p) + ("xx",)
            for p in zip(uvf.ant_1_array, uvf.ant_2_array, strict=True)
        ]
        assert list(set(sorted_pairs_object2)) == [(9, 10, "xx")]


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@cases_decorator
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
@pytest.mark.parametrize("invert", [True, False])
def test_select_times(input_uvf, uvf_mode, invert):
    uvf = input_uvf

    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    np.random.seed(0)
    old_history = uvf.history
    unique_times = np.unique(uvf.time_array)
    times_to_keep = np.random.choice(
        unique_times, size=unique_times.size // 2, replace=False
    )
    times_to_discard = unique_times[np.isin(unique_times, times_to_keep, invert=True)]

    Nblts_selected = np.sum([t in times_to_keep for t in uvf.time_array])

    uvf2 = uvf.copy()
    uvf2.select(times=times_to_discard if invert else times_to_keep, invert=invert)

    assert len(times_to_keep) == uvf2.Ntimes
    if uvf2.type == "baseline":
        n_compare = uvf2.Nblts
    else:
        n_compare = uvf2.Ntimes
    assert Nblts_selected == n_compare
    for t in times_to_keep:
        assert t in uvf2.time_array
    for t in np.unique(uvf2.time_array):
        assert t in times_to_keep

    assert utils.history._check_histories(
        old_history + "  Downselected to specific times using pyuvdata.", uvf2.history
    )
    # check that it also works with higher dimension array
    uvf2 = uvf.copy()
    uvf2.select(
        times=times_to_discard[np.newaxis] if invert else times_to_keep[np.newaxis, :],
        invert=invert,
    )

    assert len(times_to_keep) == uvf2.Ntimes
    assert Nblts_selected == n_compare
    for t in times_to_keep:
        assert t in uvf2.time_array
    for t in np.unique(uvf2.time_array):
        assert t in times_to_keep

    assert utils.history._check_histories(
        old_history + "  Downselected to specific times using pyuvdata.", uvf2.history
    )
    # check for errors associated with times not included in data
    bad_time = [np.min(unique_times) - 0.005]
    with pytest.raises(
        ValueError, match=f"Time {bad_time[0]} is not present in the time_array"
    ):
        uvf.select(times=bad_time, strict=True, invert=invert)

    # Test all w/ invert or no-match with regular
    with pytest.raises(
        ValueError, match="No data matching this time selection present in object."
    ):
        uvf.select(
            times=unique_times if invert else bad_time, strict=None, invert=invert
        )


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@cases_decorator
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
@pytest.mark.parametrize("invert", [True, False])
def test_select_frequencies(input_uvf, uvf_mode, invert):
    uvf = input_uvf

    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    np.random.seed(0)
    old_history = uvf.history

    freqs_to_keep = np.random.choice(
        uvf.freq_array.squeeze(), size=uvf.Nfreqs // 10, replace=False
    )
    freqs_to_discard = uvf.freq_array.flat[
        np.isin(uvf.freq_array.flat, freqs_to_keep, invert=True)
    ]

    uvf2 = uvf.copy()
    uvf2.select(
        frequencies=freqs_to_discard if invert else freqs_to_keep, invert=invert
    )

    assert len(freqs_to_keep) == uvf2.Nfreqs
    for f in freqs_to_keep:
        assert f in uvf2.freq_array
    for f in np.unique(uvf2.freq_array):
        assert f in freqs_to_keep

    assert utils.history._check_histories(
        old_history + "  Downselected to specific frequencies using pyuvdata.",
        uvf2.history,
    )

    # check that it also works with higher dimension array
    uvf2 = uvf.copy()
    uvf2.select(
        frequencies=(freqs_to_discard if invert else freqs_to_keep)[np.newaxis, :],
        invert=invert,
    )

    assert len(freqs_to_keep) == uvf2.Nfreqs
    for f in freqs_to_keep:
        assert f in uvf2.freq_array
    for f in np.unique(uvf2.freq_array):
        assert f in freqs_to_keep

    assert utils.history._check_histories(
        old_history + "  Downselected to specific frequencies using pyuvdata.",
        uvf2.history,
    )

    # check that selecting one frequency works
    uvf2 = uvf.copy()
    uvf2.select(
        frequencies=(
            np.hstack((freqs_to_keep[1:], freqs_to_discard))
            if invert
            else freqs_to_keep[0]
        ),
        invert=invert,
    )
    assert uvf2.Nfreqs == 1
    assert freqs_to_keep[0] in uvf2.freq_array
    for f in uvf2.freq_array:
        assert f in [freqs_to_keep[0]]

    assert utils.history._check_histories(
        old_history + "  Downselected to specific frequencies using pyuvdata.",
        uvf2.history,
    )

    # check for errors associated with frequencies not included in data
    bad_freq = [np.max(uvf.freq_array) + 100]
    with pytest.raises(
        ValueError, match=f"Frequency {bad_freq[0]} is not present in the freq_array"
    ):
        uvf.select(frequencies=bad_freq, strict=True)

    with pytest.raises(
        ValueError, match="No data matching this frequency selection exists."
    ):
        uvf.select(
            frequencies=uvf.freq_array.flatten() if invert else bad_freq,
            invert=invert,
            strict=None,
        )


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@cases_decorator
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
def test_select_freq_chans(input_uvf, uvf_mode):
    uvf = input_uvf
    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    np.random.seed(0)
    old_history = uvf.history

    old_history = uvf.history
    chans = np.random.choice(uvf.Nfreqs, 2)
    c1, c2 = np.sort(chans)
    chans_to_keep = np.arange(c1, c2)

    uvf2 = uvf.copy()
    uvf2.select(freq_chans=chans_to_keep)

    assert len(chans_to_keep) == uvf2.Nfreqs
    for chan in chans_to_keep:
        assert uvf.freq_array[chan] in uvf2.freq_array

    for f in np.unique(uvf2.freq_array):
        assert f in uvf.freq_array[chans_to_keep]

    assert utils.history._check_histories(
        old_history + "  Downselected to specific frequencies using pyuvdata.",
        uvf2.history,
    )

    # check that it also works with higher dimension array
    uvf2 = uvf.copy()
    uvf2.select(freq_chans=chans_to_keep[np.newaxis, :])

    assert len(chans_to_keep) == uvf2.Nfreqs
    for chan in chans_to_keep:
        assert uvf.freq_array[chan] in uvf2.freq_array

    for f in np.unique(uvf2.freq_array):
        assert f in uvf.freq_array[chans_to_keep]

    assert utils.history._check_histories(
        old_history + "  Downselected to specific frequencies using pyuvdata.",
        uvf2.history,
    )

    # check that it also works with invert selection
    uvf2 = uvf.copy()
    chans_to_discard = np.isin(np.arange(uvf2.Nfreqs), chans_to_keep, invert=True)
    uvf2.select(freq_chans=chans_to_discard, invert=True)

    assert len(chans_to_keep) == uvf2.Nfreqs
    for chan in chans_to_keep:
        assert uvf.freq_array[chan] in uvf2.freq_array

    for f in np.unique(uvf2.freq_array):
        assert f in uvf.freq_array[chans_to_keep]

    assert utils.history._check_histories(
        old_history + "  Downselected to specific frequencies using pyuvdata.",
        uvf2.history,
    )

    # Test selecting both channels and frequencies
    chans = np.random.choice(uvf.Nfreqs, 2)
    c1, c2 = np.sort(chans)
    chans_to_keep = np.arange(c1, c2)

    freqs_to_keep = uvf.freq_array[np.arange(c1 + 1, c2)]  # Overlaps with chans

    all_chans_to_keep = np.arange(c1, c2)

    uvf2 = uvf.copy()
    uvf2.select(frequencies=freqs_to_keep, freq_chans=chans_to_keep)

    assert len(all_chans_to_keep) == uvf2.Nfreqs
    for chan in chans_to_keep:
        assert uvf.freq_array[chan] in uvf2.freq_array

    for f in np.unique(uvf2.freq_array):
        assert f in uvf.freq_array[chans_to_keep]


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@cases_decorator
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
@pytest.mark.parametrize("invert", [True, False])
@pytest.mark.parametrize(
    "pols_to_keep,pols_to_drop", [[-5, -6], ["xx", "yy"], ["nn", "ee"], [[-5], [-6]]]
)
def test_select_polarizations(uvf_mode, pols_to_keep, pols_to_drop, input_uvf, invert):
    uvf = input_uvf
    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    np.random.seed(0)
    old_history = uvf.history

    uvf.telescope.set_feeds_from_x_orientation(
        "north", polarization_array=uvf.polarization_array
    )
    uvf2 = uvf.copy()
    uvf2.select(
        polarizations=pols_to_drop if invert else pols_to_keep,
        invert=invert,
        strict=None,
    )

    if not isinstance(pols_to_keep, list):
        pols_to_keep = [pols_to_keep]

    assert len(pols_to_keep) == uvf2.Npols
    for p in pols_to_keep:
        if isinstance(p, int):
            assert p in uvf2.polarization_array
        else:
            assert (
                utils.polstr2num(
                    p, x_orientation=uvf2.telescope.get_x_orientation_from_feeds()
                )
                in uvf2.polarization_array
            )
    for p in np.unique(uvf2.polarization_array):
        if isinstance(pols_to_keep[0], int):
            assert p in pols_to_keep
        else:
            assert p in utils.polstr2num(
                pols_to_keep,
                x_orientation=uvf2.telescope.get_x_orientation_from_feeds(),
            )

    assert utils.history._check_histories(
        old_history + "  Downselected to specific polarizations using pyuvdata.",
        uvf2.history,
    )


@pytest.mark.filterwarnings("ignore:Polarization")
@cases_decorator
@pytest.mark.parametrize(
    "pols,invert,strict,err_msg",
    [
        [-3, True, True, "Polarization -3 is not present"],
        [[-3], False, True, "Polarization -3 is not present"],
        [-3, False, None, "No data matching this polarization selection exists."],
        [[-5, -6], True, False, "No data matching this polarization selection exists."],
    ],
)
def test_select_polarizations_errors(input_uvf, pols, invert, strict, err_msg):
    uvf = input_uvf
    # check for errors associated with polarizations not included in data
    with pytest.raises(ValueError, match=err_msg):
        uvf.select(polarizations=pols, strict=strict, invert=invert)


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@cases_decorator
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
def test_select(input_uvf, uvf_mode):
    uvf = input_uvf
    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    np.random.seed(0)
    old_history = uvf.history

    # make new blts
    if uvf.type == "baseline":
        blt_inds = np.arange(uvf.Nblts - 1)
    else:
        blt_inds = None

    # new freqs
    freqs_to_keep = np.random.choice(
        uvf.freq_array.squeeze(), size=uvf.Nfreqs - 1, replace=False
    )
    # new ants
    if uvf.type == "baseline":
        unique_ants = np.unique(uvf.ant_1_array.tolist() + uvf.ant_2_array.tolist())
        ants_to_keep = np.random.choice(
            unique_ants, size=unique_ants.size - 1, replace=False
        )

    elif uvf.type == "antenna":
        unique_ants = np.unique(uvf.ant_array)
        ants_to_keep = np.random.choice(
            unique_ants, size=unique_ants.size - 1, replace=False
        )
    else:
        ants_to_keep = None

    if uvf.type == "baseline":
        #  new bls
        bls_select = np.random.choice(
            uvf.baseline_array, size=uvf.Nbls - 1, replace=False
        )
        first_ants, second_ants = uvf.baseline_to_antnums(bls_select)
        # give the conjugate bls for a few baselines
        first_ants[2:4], second_ants[2:4] = second_ants[2:4], first_ants[2:4]

        ant_pairs_to_keep = list(zip(first_ants, second_ants, strict=True))
        sorted_pairs_to_keep = [sort_bl(p) for p in ant_pairs_to_keep]

    else:
        ant_pairs_to_keep = None

    # new times
    unique_times = np.unique(uvf.time_array)
    times_to_keep = np.random.choice(
        unique_times, size=unique_times.size - 1, replace=False
    )

    # new pols
    pols_to_keep = [-5]

    # Independently count blts that should be selected
    if uvf.type == "baseline":
        blts_blt_select = [i in blt_inds for i in np.arange(uvf.Nblts)]
        blts_ant_select = [
            (a1 in ants_to_keep) & (a2 in ants_to_keep)
            for (a1, a2) in zip(uvf.ant_1_array, uvf.ant_2_array, strict=True)
        ]
        blts_pair_select = [
            sort_bl((a1, a2)) in sorted_pairs_to_keep
            for (a1, a2) in zip(uvf.ant_1_array, uvf.ant_2_array, strict=True)
        ]
        blts_time_select = [t in times_to_keep for t in uvf.time_array]
        Nblts_select = np.sum(
            [
                bi & (ai & pi) & ti
                for (bi, ai, pi, ti) in zip(
                    blts_blt_select,
                    blts_ant_select,
                    blts_pair_select,
                    blts_time_select,
                    strict=True,
                )
            ]
        )

    uvf2 = uvf.copy()
    uvf2.select(
        blt_inds=blt_inds,
        antenna_nums=ants_to_keep,
        bls=ant_pairs_to_keep,
        frequencies=freqs_to_keep,
        times=times_to_keep,
        polarizations=pols_to_keep,
    )

    if uvf.type == "baseline":
        assert Nblts_select == uvf2.Nblts
        for ant in np.unique(uvf2.ant_1_array.tolist() + uvf2.ant_2_array.tolist()):
            assert ant in ants_to_keep
    elif uvf.type == "antenna":
        for ant in np.unique(uvf2.ant_array):
            assert ant in ants_to_keep

    assert len(freqs_to_keep) == uvf2.Nfreqs
    for f in freqs_to_keep:
        assert f in uvf2.freq_array
    for f in np.unique(uvf2.freq_array):
        assert f in freqs_to_keep

    for t in np.unique(uvf2.time_array):
        assert t in times_to_keep

    assert len(pols_to_keep) == uvf2.Npols
    for p in pols_to_keep:
        assert p in uvf2.polarization_array
    for p in np.unique(uvf2.polarization_array):
        assert p in pols_to_keep

    if uvf.type == "baseline":
        assert utils.history._check_histories(
            old_history + "  Downselected to specific baseline-times, antennas, "
            "antenna pairs, times, frequencies, polarizations using pyuvdata.",
            uvf2.history,
        )
    elif uvf.type == "antenna":
        assert utils.history._check_histories(
            old_history + "  Downselected to specific antennas, times, "
            "frequencies, polarizations using pyuvdata.",
            uvf2.history,
        )
    else:
        assert utils.history._check_histories(
            old_history + "  Downselected to specific times, frequencies, "
            "polarizations using pyuvdata.",
            uvf2.history,
        )


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
def test_parse_ants_error(uvf_from_uvcal, uvf_mode):
    uvf = uvf_from_uvcal
    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    err_msg = (
        "UVFlag objects can only call 'parse_ants' function if type is 'baseline'."
    )
    with pytest.raises(ValueError, match=err_msg):
        uvf.parse_ants("all")


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.parametrize(
    "select_kwargs,err_msg",
    [
        (
            {"ant_str": "all", "antenna_nums": [1, 2, 3]},
            "Cannot provide ant_str with antenna_nums, bls, or polarizations.",
        ),
        (
            {"ant_str": "all", "bls": [(0, 1), (1, 2)]},
            "Cannot provide ant_str with antenna_nums, bls, or polarizations.",
        ),
        (
            {"ant_str": "all", "polarizations": [-5, -6, -7]},
            "Cannot provide ant_str with antenna_nums, bls, or polarizations.",
        ),
        ({"ant_str": "auto"}, "There is no data matching ant_str=auto in this object."),
        (
            {"ant_str": "9x_10x", "invert": True},
            "Cannot set invert=True if using ant_str with polarizations.",
        ),
    ],
)
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
def test_select_parse_ants_errors(uvf_from_data, uvf_mode, select_kwargs, err_msg):
    uvf = uvf_from_data
    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    if select_kwargs["ant_str"] == "auto":
        uvf = uvf.select(ant_str="cross", inplace=False)
    with pytest.raises(ValueError, match=err_msg):
        uvf.select(**select_kwargs)


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
def test_select_parse_ants(uvf_from_data, uvf_mode):
    uvf = uvf_from_data
    # used to set the mode depending on which input is given to uvf_mode
    getattr(uvf, uvf_mode)()
    uvf.select(ant_str="97_104,97_105,88_97")
    assert uvf.Nbls == 3
    assert np.array_equiv(
        np.unique(uvf.baseline_array),
        utils.antnums_to_baseline(
            *np.transpose([(88, 97), (97, 104), (97, 105)]),
            Nants_telescope=uvf.telescope.Nants,
        ),
    )


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_equality_no_history(uvf_from_data):
    uvf = uvf_from_data
    uvf2 = uvf.copy()
    assert uvf.__eq__(uvf2, check_history=True)
    uvf2.history += "different text"
    assert uvf.__eq__(uvf2, check_history=False)


@pytest.mark.filterwarnings("ignore:The uvw_array does not match the expected values")
def test_inequality_different_classes(uvf_from_data):
    uvf = uvf_from_data

    class TestClass:
        def __init__(self):
            pass

    other_class = TestClass()

    assert uvf.__ne__(other_class, check_history=False)


def test_to_antenna_collapsed_pols(uvf_from_uvcal, uvcal_obj):
    uvf = uvf_from_uvcal

    assert not uvf.pol_collapsed
    uvc = uvcal_obj

    uvf.collapse_pol()
    assert uvf.pol_collapsed
    uvf.check()

    uvf.to_waterfall()
    uvf.to_antenna(uvc, force_pol=True)
    assert not uvf.pol_collapsed
    uvf.check()


def test_to_antenna_spw_fill(uvf_from_uvcal, uvcal_obj):
    uvf = uvf_from_uvcal
    uvc = uvcal_obj

    uvf.to_waterfall()
    # Muck spw-related attributes to see if it gets pulled from main object
    uvf.Nspws = uvf.spw_array = uvf.flex_spw_id_array = None
    uvf.to_antenna(uvc)

    uvf.check()
    assert np.array_equal(uvf.spw_array, uvc.spw_array)
    assert np.array_equal(uvf.flex_spw_id_array, uvc.flex_spw_id_array)
    assert uvf.Nspws == uvc.Nspws


def test_get_ants_error(uvf_from_waterfall):
    uvf = uvf_from_waterfall

    with pytest.raises(
        ValueError, match="A waterfall type UVFlag object has no sense of antennas."
    ):
        uvf.get_ants()


@cases_decorator_no_waterfall
@pytest.mark.parametrize("uvf_mode", ["to_flag", "to_metric"])
def test_get_ants(input_uvf, uvf_mode):
    uvf = input_uvf
    getattr(uvf, uvf_mode)()
    ants = uvf.get_ants()
    if uvf.type == "baseline":
        expected_ants = np.sort(
            list(set(np.unique(uvf.ant_1_array)).union(np.unique(uvf.ant_2_array)))
        )
    if uvf.type == "antenna":
        expected_ants = np.unique(uvf.ant_array)

    assert np.array_equiv(ants, expected_ants)
