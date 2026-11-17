from __future__ import annotations

import html
import math
import re
from pathlib import Path

import gemmi

from .http import SourceError
from .util import atomic_write, digest, doi_normalize, plain, safe_filename

METALS = set("Li Na K Rb Cs Be Mg Ca Sr Ba Sc Ti V Cr Mn Fe Co Ni Cu Zn Y Zr Nb Mo Tc Ru Rh Pd Ag Cd "
             "Hf Ta W Re Os Ir Pt Au Hg Al Ga In Tl Ge Sn Pb As Sb Bi La Ce Pr Nd Sm Eu Gd Tb Dy Ho Er Tm Yb Lu".split())
HALIDES = {"F", "Cl", "Br", "I"}


def elements(formula):
    return set(re.findall(r"[A-Z][a-z]?", formula or ""))


def field(block, *tags):
    for tag in tags:
        value = block.find_value(tag)
        if value and value not in {"?", "."}:
            return plain(gemmi.cif.as_string(value))
    return ""


def inspect_cif(path: Path):
    try:
        document = gemmi.cif.read_file(str(path))
    except (ValueError, RuntimeError) as exc:
        raise SourceError(f"CIF inválido: {type(exc).__name__}.") from None
    blocks = []
    for block in document:
        item = {"block": block.name, "formula": field(block, "_chemical_formula_sum"),
                "moiety": field(block, "_chemical_formula_moiety"),
                "chemical_name": field(block, "_chemical_name_systematic", "_chemical_name_common"),
                "doi": doi_normalize(field(block, "_journal_paper_doi")),
                "space_group": field(block, "_space_group_name_H-M_alt", "_symmetry_space_group_name_H-M"),
                "temperature_k": field(block, "_diffrn_ambient_temperature", "_cell_measurement_temperature"),
                "r_factor": field(block, "_refine_ls_R_factor_gt", "_refine_ls_R_factor_obs"),
                "warnings": []}
        try:
            crystal = gemmi.make_small_structure_from_block(block)
            cell = crystal.cell
            sites = list(crystal.sites)
            coords = [list(block.find_values(f"_atom_site_fract_{axis}")) for axis in "xyz"]
            valid_coords = bool(sites) and all(len(c) == len(sites) for c in coords)
            if valid_coords:
                valid_coords = all(math.isfinite(gemmi.cif.as_number(v)) for c in coords for v in c)
            item["has_coordinates"] = valid_coords and cell.is_crystal()
            item["cell"] = dict(zip(("a", "b", "c", "alpha", "beta", "gamma"), cell.parameters))
            item["cell"]["volume"] = cell.volume
            item["sites_asymmetric_unit"] = len(sites)
            el = {s.element.name for s in sites} or elements(item["formula"])
            item["elements"] = sorted(el)
            item["hybrid_composition_candidate"] = "C" in el and bool(el & METALS)
            item["metal_halide_candidate"] = item["hybrid_composition_candidate"] and bool(el & HALIDES)
            if any(s.occ < 0.999 for s in sites):
                item["warnings"].append("Ocupações parciais/desordem: revisar modelo estrutural.")
            if item["has_coordinates"]:
                item["preview_atoms"] = [{"element": s.element.name,
                                          "xyz": list(cell.orthogonalize(s.fract))} for s in sites[:500]]
        except (ValueError, RuntimeError):
            item["has_coordinates"] = False
            item["warnings"].append("Não foi possível ler coordenadas/cela com Gemmi.")
        if not item.get("has_coordinates"):
            item["warnings"].append("Bloco sem coordenadas fracionárias e cela válidas.")
        blocks.append(item)
    if not blocks:
        raise SourceError("CIF sem blocos de dados.")
    return {"sha256": digest(path.read_bytes()), "blocks": blocks,
            "valid_structure": any(b.get("has_coordinates") for b in blocks),
            "note": "Cela e coordenadas não comprovam identidade do orgânico, topologia ou semicondutividade."}


def obtain_structure(structure, directory, http):
    if structure.get("path"):
        path = (directory / structure["path"]).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise SourceError("Caminho CIF fora da pasta de execução.")
    elif structure.get("url"):
        path = directory / "structures" / (safe_filename(structure["id"]) + ".cif")
        body = http.get(structure["url"])
        atomic_write(path, body)
    else:
        return structure | {"availability": "metadata_only", "note": "Fonte sem URL CIF; consulte o depósito/artigo."}
    info = inspect_cif(path)
    preview = path.with_suffix(".svg")
    atoms = next((b.get("preview_atoms", []) for b in info["blocks"] if b.get("has_coordinates")), [])
    if atoms:
        atomic_write(preview, preview_svg(atoms))
    return structure | {"path": str(path.relative_to(directory)), "cif": info,
                        "preview": str(preview.relative_to(directory)) if atoms else None,
                        "availability": "downloaded" if info["valid_structure"] else "invalid_coordinates"}


def preview_svg(atoms):
    colors = {"C": "#475569", "N": "#2563eb", "O": "#ef4444", "H": "#d1d5db", "Pb": "#7c3aed",
              "I": "#a21caf", "Br": "#b45309", "Cl": "#16a34a", "S": "#ca8a04", "Sn": "#0891b2"}
    points = [(a["xyz"][0] - 0.5 * a["xyz"][2], a["xyz"][1] - 0.3 * a["xyz"][2], a["element"]) for a in atoms]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    scale = min(340 / max(max(xs) - min(xs), 1), 210 / max(max(ys) - min(ys), 1))
    circles = []
    for x, y, el in points:
        circles.append(f'<circle cx="{30 + (x - min(xs)) * scale:.2f}" cy="{30 + (y - min(ys)) * scale:.2f}" '
                       f'r="{3 if el == "H" else 6}" fill="{colors.get(el, "#db2777")}"><title>{html.escape(el)}</title></circle>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 290"><rect width="400" height="290" fill="#f8fafc"/>' + \
        "".join(circles) + '<text x="15" y="275" font-size="11">Unidade assimétrica · projeção sem ligações · até 500 sítios</text></svg>'
