#!/usr/bin/env python3
"""Attach saved two-chain OpenFold3 MSAs to ligand-screening queries."""

import argparse
import json
from pathlib import Path


def chain_key(chain):
    ids = chain.get("chain_ids")
    if isinstance(ids, str):
        ids = [ids]
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
        raise ValueError(f"Invalid protein chain_ids: {ids!r}")
    return tuple(ids)


def protein_chains(query):
    chains = [
        c for c in query.get("chains", [])
        if str(c.get("molecule_type", "")).lower() == "protein"
    ]
    if len(chains) != 2:
        raise ValueError("Every query must contain exactly two protein chains")
    return chains


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query_json", type=Path)
    parser.add_argument("msa_dir", type=Path, help="Folder containing query_msa.json")
    parser.add_argument("--output", type=Path, help="Write the enriched query JSON here")
    args = parser.parse_args()

    query_set = json.loads(args.query_json.read_text())
    saved = json.loads((args.msa_dir / "query_msa.json").read_text())
    if not isinstance(query_set.get("queries"), dict) or not query_set["queries"]:
        raise ValueError("Input JSON must contain a nonempty queries object")
    saved_queries = saved.get("queries", {})
    if len(saved_queries) != 1:
        raise ValueError("Saved MSA must come from exactly one reference complex")
    reference = next(iter(saved_queries.values()))
    reference_chains = {chain_key(c): c for c in protein_chains(reference)}
    if len(reference_chains) != 2:
        raise ValueError("Reference protein chain IDs must be distinct")
    heteromer = len({c.get("sequence") for c in reference_chains.values()}) == 2

    for key, chain in reference_chains.items():
        if not chain.get("main_msa_file_paths"):
            raise ValueError(f"Reference chain {key} has no main MSA")
        if heteromer and not chain.get("paired_msa_file_paths"):
            raise ValueError(f"Reference chain {key} has no paired MSA for this heteromer")
        for field in ("main_msa_file_paths", "paired_msa_file_paths"):
            paths = chain.get(field) or []
            if isinstance(paths, str):
                paths = [paths]
            for path in paths:
                container_path = Path(path)
                if not container_path.is_absolute() or not container_path.is_relative_to("/msas"):
                    raise ValueError(f"MSA path must be under /msas: {path}")
                host_path = args.msa_dir / container_path.relative_to("/msas")
                if not host_path.exists():
                    raise ValueError(f"Saved MSA file is missing: {host_path}")

    for name, query in query_set["queries"].items():
        chains = protein_chains(query)
        if {chain_key(c) for c in chains} != set(reference_chains):
            raise ValueError(f"{name}: protein chain IDs differ from the reference complex")
        for chain in chains:
            reference_chain = reference_chains[chain_key(chain)]
            if chain.get("sequence") != reference_chain.get("sequence"):
                raise ValueError(f"{name}: protein sequence differs for chain {chain_key(chain)}")
            for field in ("main_msa_file_paths", "paired_msa_file_paths"):
                if reference_chain.get(field):
                    chain[field] = reference_chain[field]
        query["use_msas"] = True

    print(f"Validated {len(query_set['queries'])} queries against the saved two-chain MSAs")
    if args.output:
        args.output.write_text(json.dumps(query_set, indent=2) + "\n")
        print(f"Prepared query JSON: {args.output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"MSA query preparation failed: {error}") from error
