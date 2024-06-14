import os
from pathlib import Path
import xarray as xr
import shutil
import pytest
from tempfile import mkdtemp

from wavespectra import read_ncswan, read_octopus
from wavespectra.core.attributes import attrs


FILES_DIR = Path(__file__).parent / "../sample_files"


class TestOctopus(object):
    """Test Octopus writer."""

    @classmethod
    def setup_class(self):
        """Setup class."""
        self.tmp_dir = mkdtemp()
        self.ncswanfile = os.path.join(FILES_DIR, "swanfile.nc")
        self.octopusfile = os.path.join(FILES_DIR, "octopusfile.oct")

    @classmethod
    def teardown_class(self):
        shutil.rmtree(self.tmp_dir)

    def test_read_octopus(self):
        ds = read_octopus(self.octopusfile)

    def test_write_octopus(self):
        ds = read_ncswan(self.ncswanfile)
        ds.spec.to_octopus(os.path.join(self.tmp_dir, "spectra.oct"))

    def test_write_octopus_site_as_variable(self):
        ds = read_ncswan(self.ncswanfile).isel(site=0)
        ds.spec.to_octopus(os.path.join(self.tmp_dir, "spectra.oct"))

    def test_write_octopus_latlon_as_dims(self):
        ds = read_ncswan(self.ncswanfile).isel(site=0).set_coords(("lon", "lat"))
        ds.spec.to_octopus(os.path.join(self.tmp_dir, "spectra.oct"))

    def test_write_octopus_dims_ordering(self):
        ds = read_ncswan(self.ncswanfile).transpose("site", "time", ...)
        ds.spec.to_octopus(os.path.join(self.tmp_dir, "spectra.oct"))

    def test_write_octopus_no_latlon_specify(self):
        ds = read_ncswan(self.ncswanfile).drop_vars(("lon", "lat"))
        lons = [180.0]
        lats = [-30.0]
        filename = os.path.join(self.tmp_dir, "spectra.oct")
        ds.spec.to_octopus(filename, lons=lons, lats=lats)
        ds2 = read_octopus(filename)
        assert sorted(ds2.lon.values) == sorted(lons)
        assert sorted(ds2.lat.values) == sorted(lats)

    def test_write_octopus_no_latlon_do_not_specify(self):
        ds = read_ncswan(self.ncswanfile).drop_vars(("lon", "lat"))
        filename = os.path.join(self.tmp_dir, "spectra.oct")
        ds.spec.to_octopus(filename)
        ds2 = read_octopus(filename)
        assert list(ds2.lon.values) == list(ds2.lon.values * 0)
        assert list(ds2.lat.values) == list(ds2.lat.values * 0)

    def test_write_octopus_and_read(self):
        ds = read_ncswan(self.ncswanfile)
        file = os.path.join(self.tmp_dir, "spectra.oct")
        ds.spec.to_octopus(file)
        read_back = read_octopus(file)
        assert ds.spec.hs().values == pytest.approx(
            read_back.spec.hs().values, rel=1e-3
        )

    def test_write_octopus_missing_winds_depth(self):
        ds = read_ncswan(self.ncswanfile)
        ds = ds.drop_vars([attrs.WSPDNAME, attrs.WDIRNAME, attrs.DEPNAME])
        ds.spec.to_octopus(os.path.join(self.tmp_dir, "spec_no_winds_depth.oct"))

    def test_write_octopus_one_time(self):
        ds = read_ncswan(self.ncswanfile)
        ds = ds.isel(time=[0])
        ds.spec.to_octopus(os.path.join(self.tmp_dir, "spec_one_time.oct"))
