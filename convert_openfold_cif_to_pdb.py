#!/usr/bin/env python3
"""Convert OpenFold3 CIF predictions into an OpenBind challenge PDB submission.

Adapted from the Biotite conversion helper in the OpenBind Challenge 1 tutorial.
The input directory must contain one *_model.cif per ligand query, nested under
<query_id>/seed_*/. The ligand table must have id and smiles columns.
"""

import argparse
import csv
import os
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

import biotite.structure.io as strucio
import numpy as np


def read_expected_ids(path: Path) -> set[str]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames and "id" in reader.fieldnames:
            id_column = "id"
        elif reader.fieldnames and "Molecule_Name" in reader.fieldnames:
            id_column = "Molecule_Name"
        else:
            raise ValueError("Ligand CSV must have an id or Molecule_Name column")
        ids = [(row[id_column] or "").strip() for row in reader]
    if len(ids) != 400 or len(set(ids)) != 400 or any(not name for name in ids):
        raise ValueError("Ligand CSV must contain 400 distinct, nonempty IDs")
    return set(ids)


def convert_one(source: Path, destination: Path) -> None:
    # Same load, rename, and save approach as the challenge tutorial notebook.
    structure = strucio.load_structure(str(source))
    if len(structure) == 0:
        raise ValueError(f"Empty structure: {source}")
    ligand = structure.res_name == "LIG0"
    if not np.any(ligand):
        raise ValueError(f"No LIG0 ligand found: {source}")
    if len(set(zip(structure.chain_id[ligand], structure.res_id[ligand]))) != 1:
        raise ValueError(f"Expected one ligand residue: {source}")
    if set(structure.chain_id) != {"A", "B", "C"}:
        raise ValueError(f"Expected protein chains A/B and ligand chain C: {source}")
    structure.res_name[ligand] = "LIG"
    strucio.save_structure(str(destination), structure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="OpenFold3 prediction output directory")
    parser.add_argument("output_dir", type=Path, help="New directory for 400 PDB files")
    parser.add_argument("--ligands-csv", required=True, type=Path, help="CSV with expected id values")
    parser.add_argument("--zip", dest="zip_path", required=True, type=Path, help="Submission ZIP to create")
    args = parser.parse_args()

    expected = read_expected_ids(args.ligands_csv)
    sources = list(args.input_dir.glob("*/seed_*/*_model.cif"))
    by_id = {}
    for source in sources:
        name = source.parent.parent.name
        if name in by_id:
            raise ValueError(f"Multiple CIF predictions for {name}; choose one seed/sample first")
        by_id[name] = source
    if set(by_id) != expected:
        missing = sorted(expected - set(by_id))
        extra = sorted(set(by_id) - expected)
        raise ValueError(f"Input CIF IDs do not match ligand CSV: {len(missing)} missing, {len(extra)} extra")
    if args.output_dir.exists():
        raise ValueError(f"Output directory already exists: {args.output_dir}")
    if args.zip_path.exists():
        raise ValueError(f"ZIP already exists: {args.zip_path}")
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    args.zip_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pdb-conversion-", dir=args.output_dir.parent) as temporary:
        staged = Path(temporary)
        for count, name in enumerate(sorted(expected), 1):
            convert_one(by_id[name], staged / f"{name}.pdb")
            if count % 50 == 0 or count == len(expected):
                print(f"Converted {count}/{len(expected)} CIF files", flush=True)
        os.replace(staged, args.output_dir)

    with ZipFile(args.zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for name in sorted(expected):
            archive.write(args.output_dir / f"{name}.pdb", arcname=f"{name}.pdb")
    print(f"PDB files: {args.output_dir}")
    print(f"Submission ZIP: {args.zip_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Conversion failed: {error}") from error
