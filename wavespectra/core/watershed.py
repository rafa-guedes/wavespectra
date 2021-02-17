"""Watershed partitioning."""
import numpy as np
import xarray as xr

from wavespectra.specarray import celerity
from wavespectra.core.attributes import attrs
from wavespectra.specpart import specpart
from wavespectra.core.misc import D2R, R2D


_ = np.newaxis


def nppart(spectrum, freq, dir, wspd, wdir, dpt, swells=3, agefac=1.7, wscut=0.3333):
    """Watershed partition on a numpy array."""

    all_parts = []

    part_array = specpart.partition(spectrum)

    Up = agefac * wspd * np.cos(D2R * (dir - wdir))
    windbool = np.tile(Up, (freq.size, 1)) > np.tile(
        celerity(freq, dpt)[:, np.newaxis], (1, dir.size)
    )

    ipeak = 1  # values from specpart.partition start at 1
    part_array_max = part_array.max()
    # partitions_hs_swell = np.zeros(part_array_max + 1)  # zero is used for sea
    partitions_hs_swell = np.zeros(part_array_max + 1)  # zero is used for sea
    while ipeak <= part_array_max:
        part_spec = np.where(part_array == ipeak, spectrum, 0.0)

        # Assign new partition if multiple valleys and satisfying conditions
        __, imin = inflection(part_spec, freq, dfres=0.01, fmin=0.05)
        if len(imin) > 0:
            part_spec_new = part_spec.copy()
            part_spec_new[imin[0].squeeze() :, :] = 0
            newpart = part_spec_new > 0
            if newpart.sum() > 20:
                part_spec[newpart] = 0
                part_array_max += 1
                part_array[newpart] = part_array_max
                partitions_hs_swell = np.append(partitions_hs_swell, 0)

        # Assign sea partition
        W = part_spec[windbool].sum() / part_spec.sum()
        if W > wscut:
            part_array[part_array == ipeak] = 0
        else:
            partitions_hs_swell[ipeak] = hs(part_spec, freq, dir)

        ipeak += 1

    sorted_swells = np.flipud(partitions_hs_swell[1:].argsort() + 1)
    parts = np.concatenate(([0], sorted_swells[:swells]))
    for part in parts:
        all_parts.append(np.where(part_array == part, spectrum, 0.0))

    # Extend partitions list if it is less than swells
    if len(all_parts) < swells + 1:
        nullspec = 0 * spectrum
        nmiss = (swells + 1) - len(all_parts)
        for i in range(nmiss):
            all_parts.append(nullspec)
    
    return np.array(all_parts)


def partition(
    dset,
    wspd="wspd",
    wdir="wdir",
    dpt="dpt",
    swells=3,
    agefac=1.7,
    wscut=0.3333,
    hs_min=0.001,
):
    """Watershed partitioning.

    Args:
        - dset (xr.Dataset): Wave spectra dataset in wavespectra convention.
        - wspd (xr.DataArray, str): Wind speed DataArray or variable name in dset.
        - wdir (xr.DataArray, str): Wind direction DataArray or variable name in dset.
        - dpt (xr.DataArray, str): Depth DataArray or the variable name in dset.
        - swells (int): Number of swell partitions to compute.
        - agefac (float): Age factor.
        - wscut (float): Wind speed cutoff.
        - hs_min (float): minimum Hs for assigning swell partition.

    Returns:
        - dspart (xr.Dataset): Partitioned spectra dataset with extra dimension.

    References:
        - Hanson, Jeffrey L., et al. "Pacific hindcast performance of three
            numerical wave models." JTECH 26.8 (2009): 1614-1633.

    """
    # Sort out inputs
    if isinstance("wspd", str):
        wspd = dset[wspd]
    if isinstance("wdir", str):
        wdir = dset[wdir]
    if isinstance("dpt", str):
        dpt = dset[dpt]

    # Partitioning full spectra
    dsout = xr.apply_ufunc(
        nppart,
        dset.efth,
        dset.freq,
        dset.dir,
        dset.wspd,
        dset.wdir,
        dset.dpt,
        swells,
        agefac,
        wscut,
        input_core_dims=[["freq", "dir"], ["freq"], ["dir"], [], [], [], [], [], []],
        output_core_dims=[["part", "freq", "dir"]],
        vectorize=True,
        dask="parallelized",
        output_dtypes=["float32"],
        dask_gufunc_kwargs={
            "output_sizes": {
                "part": swells + 1,
            },
        },
    )

    # Finalise output
    dsout.name = "efth"
    dsout["part"] = np.arange(swells + 1)
    dsout.part.attrs={"standard_name": "spectral_partition_number", "units": ""}

    return dsout.transpose("part", ...)


def hs(spectrum, freq, dir, tail=True):
    """Significant wave height Hmo.

    Args:
        - spectrum (2darray): wave spectrum array
        - freq (1darray): wave frequency array
        - dir (1darray): wave direction array
        - tail (bool): if True fit high-frequency tail before integrating spectra

    """
    df = abs(freq[1:] - freq[:-1])
    if len(dir) > 1:
        ddir = abs(dir[1] - dir[0])
        E = ddir * spectrum.sum(1)
    else:
        E = np.squeeze(spectrum)
    Etot = 0.5 * sum(df * (E[1:] + E[:-1]))
    if tail and freq[-1] > 0.333:
        Etot += 0.25 * E[-1] * freq[-1]
    return 4.0 * np.sqrt(Etot)


def partition2(
    dset,
    wspd="wspd",
    wdir="wdir",
    dpt="dpt",
    agefac=1.7,
    wscut=0.3333,
    hs_min=0.001,
    max_swells=5
):
    """Watershed partitioning.

    Args:
        - dset (xr.Dataset): Wave spectra dataset in wavespectra convention.
        - wspd (xr.DataArray, str): Wind speed DataArray or variable name in dset.
        - wdir (xr.DataArray, str): Wind direction DataArray or variable name in dset.
        - dpt (xr.DataArray, str): Depth DataArray or the variable name in dset.
        - agefac (float): Age factor.
        - wscut (float): Wind speed cutoff.
        - hs_min (float): minimum Hs for assigning swell partition.
        - max_swells: maximum number of swells to extract

    Returns:
        - dspart (xr.Dataset): Partitioned spectra dataset with extra dimension.

    References:
        - Hanson, Jeffrey L., et al. "Pacific hindcast performance of three
            numerical wave models." JTECH 26.8 (2009): 1614-1633.

    """
    # Sort out inputs
    if isinstance("wspd", str):
        wspd = dset[wspd]
    if isinstance("wdir", str):
        wdir = dset[wdir]
    if isinstance("dpt", str):
        dpt = dset[dpt]

    dsout = xr.apply_ufunc(
        specpart.partition,
        dset.efth,
        input_core_dims=[["freq", "dir"]],
        output_core_dims=[["freq", "dir"]],
        # exclude_dims=set(("freq", "dir")),
        vectorize=True,
        dask="parallelized",
        output_dtypes=["int32"],
    )

    Up = agefac * wspd * np.cos(D2R * (dset.dir - wdir))
    windbool = celerity(dset.freq, dpt) < Up

    ipeak = 1  # values from specpart.partition start at 1
    part_array_max = dsout.max()
    # partitions_hs_swell = np.zeros(part_array_max + 1)  # zero is used for sea

    part_spec = dset.efth.where(dsout != 1, 0.0)

    W = part_spec.where(windbool).sum(dim=["freq", "dir"]) / part_spec.sum(dim=["freq", "dir"])

    dsout = dsout.where(W <= wscut, 0)

    fig = plt.figure()
    dsout.sortby("dir").plot()
    plt.title("Partition array")

    fig = plt.figure()
    part_spec.sortby("dir").plot()
    plt.title("Filtered partition array")

    fig = plt.figure()
    windbool.sortby("dir").plot()
    plt.title("Wind criteria")

    plt.show()

    import ipdb; ipdb.set_trace()

    # windbool = np.tile(Up, (nfreq, 1)) > np.tile(
    #     celerity(freqs, dep)[:, _], (1, ndir)
    # )

    return dsout


def frequency_resolution(freq):
    """Frequency resolution array."""
    if len(freq) > 1:
        return abs(freq[1:] - freq[:-1])
    else:
        return np.array((1.0,))


def inflection(spectrum, freq, dfres=0.01, fmin=0.05):
    """Finds points of inflection in smoothed frequency spectra.

    Args:
        fdspec (ndarray): freq-dir 2D specarray.
        dfres (float): used to determine length of smoothing window.
        fmin (float): minimum frequency for looking for minima/maxima.

    """
    if len(freq) > 1:
        df = frequency_resolution(freq)
        sf = spectrum.sum(axis=1)
        nsmooth = int(dfres / df[0])  # Window size
        if nsmooth > 1:
            sf = np.convolve(sf, np.hamming(nsmooth), "same")  # Smoothed f-spectrum
        sf[(sf < 0) | (freq < fmin)] = 0
        diff = np.diff(sf)
        imax = np.argwhere(np.diff(np.sign(diff)) == -2) + 1
        imin = np.argwhere(np.diff(np.sign(diff)) == 2) + 1
    else:
        imax = 0
        imin = 0
    return imax, imin


if __name__ == "__main__":

    import matplotlib.pyplot as plt
    from wavespectra import read_ww3, read_wavespectra

    print("Testing watershed")

    # dset = read_ww3("/source/wavespectra/tests/sample_files/ww3file.nc")
    dset = read_wavespectra("/source/consultancy/jogchum/route/route_feb21/p04/spec.nc")

    ds = dset.isel(time=slice(None, 1000)).drop_dims("fastsite").sortby("dir")#.chunk({"time": 5000})#.load()


    # #============
    # # Old method
    # #============
    # dsout0 = ds.spec.partition(wsp_darr=ds.wspd, wdir_darr=ds.wdir, dep_darr=ds.dpt)
    # hs0 = dsout0.spec.hs()

    #============
    # New method
    #============
    dsout = partition(
        ds,
        wspd="wspd",
        wdir="wdir",
        dpt="dpt",
        swells=3,
        agefac=1.7,
        wscut=0.3333,
        hs_min=0.001,
    )
    hs = dsout.spec.hs().load()
