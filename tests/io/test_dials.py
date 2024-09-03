import io
import logging
import os
from contextlib import redirect_stdout

import gemmi
import msgpack
import numpy as np
import pandas

import reciprocalspaceship as rs
from reciprocalspaceship.io import read_dials_stills


def make_refls(unit_cell, sg, seed=8675309):
    np.random.seed(seed)

    data = {
        "miller_index": "cctbx::miller::index<>",
        "intensity.sum.value": "double",
        "intensity.sum.variance": "double",
        "id": "int",
        "global_refl_index": "int",
        "xyz": "vec3<double>",
    }

    datasets = []
    shot_start = 0
    expts_per_refl = 5
    refls_per_file = 100000
    pack_names = []
    for i_file in range(2):
        hkl = np.random.randint(-100, 100, (refls_per_file, 3)).astype(np.int32)
        I = (-500 + np.random.random(refls_per_file) * 1000).astype(np.float64)
        varI = (np.random.random(refls_per_file) * 1000 + 1e-6).astype(np.float64)
        ids = np.sort([i % expts_per_refl for i in range(refls_per_file)]).astype(
            np.int32
        )
        xyz = np.random.uniform(-1000, 1000, (refls_per_file, 3)).astype(np.float64)
        global_index = (np.arange(refls_per_file) + refls_per_file * i_file).astype(
            np.int32
        )
        ds = rs.DataSet(
            {
                "H": hkl[:, 0],
                "K": hkl[:, 1],
                "L": hkl[:, 2],
                "I": I,
                "varI": varI,
                "id": ids,
                "xyz0": xyz[:, 0],
                "xyz1": xyz[:, 1],
                "xyz2": xyz[:, 2],
                "global_refl_index": global_index,
            },
            cell=unit_cell,
            spacegroup=sg,
        )
        datasets.append(ds)

        file_data = {**data}
        for key, vals in zip(
            [
                "miller_index",
                "intensity.sum.value",
                "intensity.sum.variance",
                "id",
                "xyz",
                "global_refl_index",
            ],
            [hkl, I, varI, ids, xyz, global_index],
        ):
            dtype = file_data[key]
            file_data[key] = dtype, (refls_per_file, vals.tobytes())
        idents = {i: f"experiment{i+shot_start}" for i in range(expts_per_refl)}

        pack = (
            "dials::af::reflection_table",
            1,
            {"identifiers": idents, "nrows": refls_per_file, "data": file_data},
        )

        pack_name = f"test.rs.io.dials.pack{i_file}.refl"
        with open(pack_name, "wb") as o:
            msgpack.dump(pack, o)
        pack_names.append(pack_name)

        shot_start += expts_per_refl

    ds0 = rs.concat(datasets)
    ds0.set_index(["H", "K", "L"], inplace=True, drop=True)
    return ds0, pack_names


def test_dials_reader(verbose=False):

    unit_cell = 78, 78, 235, 90, 90, 120
    sg = "P6522"

    ds0, pack_names = make_refls(unit_cell, sg)
    # read without parallelization
    ds1 = read_dials_stills(
        pack_names, unit_cell, sg, parallel_backend=None, numjobs=1, verbose=verbose
    )
    gemmi_unit_cell = gemmi.UnitCell(*unit_cell)
    gemmi_sg = gemmi.SpaceGroup(sg)
    assert ds1.spacegroup == gemmi_sg
    assert ds1.cell == gemmi_unit_cell

    # read with parallelization
    ds2 = read_dials_stills(
        pack_names,
        gemmi_unit_cell,
        gemmi_sg,
        parallel_backend="ray",
        numjobs=2,
        verbose=verbose,
    )
    assert ds1.equals(ds2)
    assert "xyz.0" not in ds2

    # read extra columns including global index and compare with ds0
    ds3 = read_dials_stills(
        pack_names,
        gemmi_unit_cell,
        gemmi_sg,
        parallel_backend="ray",
        numjobs=2,
        extra_cols=["xyz", "global_refl_index"],
        verbose=verbose,
    )
    assert "xyz.0" in ds3
    ds3.reset_index(inplace=True)
    ds0.reset_index(inplace=True)

    df_m = pandas.merge(ds3, ds0, how="inner", on="global_refl_index")

    assert np.allclose(df_m.H_x, df_m.H_y)
    assert np.allclose(df_m.K_x, df_m.K_y)
    assert np.allclose(df_m.L_x, df_m.L_y)
    assert np.allclose(df_m.xyz0, df_m["xyz.0"])
    assert np.allclose(df_m.xyz1, df_m["xyz.1"])
    assert np.allclose(df_m.xyz2, df_m["xyz.2"])
    assert np.allclose(df_m.I, df_m["intensity.sum.value"])
    assert np.allclose(df_m.varI, df_m["intensity.sum.sigma"] ** 2)

    for f in pack_names:
        os.remove(f)


def test_verbosity():
    unit_cell = 78, 78, 230, 90, 90, 120
    sg = "P6"
    ds, pack_names = make_refls(unit_cell=unit_cell, sg=sg)

    logger_out = io.StringIO()
    logger = logging.getLogger("rs.io.dials")
    for handler in logger.handlers:
        handler.setStream(logger_out)

    other_out = io.StringIO()
    with redirect_stdout(other_out):
        read_dials_stills(
            pack_names, ds.cell, ds.spacegroup, parallel_backend=None, verbose=False
        )

    assert not other_out.getvalue()
    assert not logger_out.getvalue()

    read_dials_stills(
        pack_names, ds.cell, ds.spacegroup, parallel_backend=None, verbose=True
    )

    assert logger_out.getvalue()


if __name__ == "__main__":
    test_verbosity()
    print("Verbosity test passed.")
    test_dials_reader(verbose=True)
    print("Reader test passed.")
