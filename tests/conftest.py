import pytest

from perovskite_explorer.identity import read_compounds
from perovskite_explorer.pipeline import initialize
from perovskite_explorer.store import Store


@pytest.fixture
def compound(tmp_path):
    path = tmp_path / "input.txt"
    path.write_text("Phenazine\n", encoding="utf-8")
    return read_compounds(path)[0]


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "input.txt"
    path.write_text("Phenazine\n", encoding="utf-8")
    directory = tmp_path / "run"
    initialize(directory, path, {"sources": ["crossref"], "max_aliases": 1,
                                 "download_cifs": False, "fulltext": False, "follow_dois": False})
    result = Store(directory)
    yield result
    result.close()


@pytest.fixture
def cif(tmp_path):
    # Synthetic test fixture, intentionally NOT an experimentally reported sample.
    path = tmp_path / "synthetic.cif"
    path.write_text('''data_synthetic_test_only
_chemical_name_systematic 'phenazinium lead iodide TEST FIXTURE'
_chemical_formula_sum 'C12 H10 N2 Pb I4'
_cell_length_a 10
_cell_length_b 11
_cell_length_c 12
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
C1 C 0.1 0.2 0.3 1
N1 N 0.2 0.3 0.4 1
Pb1 Pb 0.5 0.5 0.5 1
I1 I 0.6 0.5 0.5 0.5
''')
    return path
