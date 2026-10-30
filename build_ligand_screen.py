#!/usr/bin/env python3
"""Build a multi-query OpenFold3 JSON from one two-chain target and a ligand CSV."""

import argparse
import copy
import csv
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_json", type=Path, help="One query with the two target protein chains")
    parser.add_argument("ligands_csv", type=Path, help="CSV with id/smiles or Molecule_Name/SMILES columns")
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    reference = json.loads(args.reference_json.read_text()).get("queries", {})
    if len(reference) != 1:
        raise ValueError("Reference JSON must contain exactly one query")
    chains = next(iter(reference.values())).get("chains", [])
    proteins = [c for c in chains if c.get("molecule_type") == "protein"]
    ligands = [c for c in chains if c.get("molecule_type") == "ligand"]
    if len(proteins) != 2 or len(ligands) > 1 or len(chains) != len(proteins) + len(ligands):
        raise ValueError("Reference must have two protein chains and at most one ligand")
    for protein in proteins:
        for field in ("main_msa_file_paths", "paired_msa_file_paths"):
            protein.pop(field, None)

    ligand = copy.deepcopy(ligands[0]) if ligands else {"molecule_type": "ligand", "chain_ids": ["C"]}
    ligand.pop("ccd_codes", None)
    ligand.pop("ligand_name", None)
    queries = {}
    with args.ligands_csv.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames and {"id", "smiles"}.issubset(reader.fieldnames):
            id_column, smiles_column = "id", "smiles"
        elif reader.fieldnames and {"Molecule_Name", "SMILES"}.issubset(reader.fieldnames):
            id_column, smiles_column = "Molecule_Name", "SMILES"
        else:
            raise ValueError("Ligand CSV must have id/smiles or Molecule_Name/SMILES columns")
        for row in reader:
            name = (row[id_column] or "").strip()
            smiles = (row[smiles_column] or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise ValueError(f"Invalid ligand id {name!r}; use letters, digits, _ or -")
            if not smiles:
                raise ValueError(f"Missing SMILES for {name}")
            if name in queries:
                raise ValueError(f"Duplicate ligand id: {name}")
            ligand_chain = copy.deepcopy(ligand)
            ligand_chain["smiles"] = smiles
            queries[name] = {"chains": copy.deepcopy(proteins) + [ligand_chain]}
    if not queries:
        raise ValueError("Ligand CSV has no rows")

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps({"queries": queries}, indent=2) + "\n")
    print(f"Wrote {len(queries)} ligand queries to {args.output_json}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Ligand screen preparation failed: {error}") from error
