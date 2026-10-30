# Run record: 400-ligand OpenBind-0 screen

This is a record of the local run on **2026-10-29**, before any challenge-portal submission. It distinguishes checks that succeeded locally from pose accuracy, which can only be measured against withheld references.

## Hardware and software

| Item | Recorded value |
| --- | --- |
| Host | NVIDIA DGX Spark, ARM64, GB10 GPU |
| NVIDIA driver | 580.142 |
| Base image | `nvcr.io/nvidia/pytorch:25.11-py3` |
| Local image | `openbind-dgx-spark:0.5.0` |
| Local image ID | `sha256:0c21838677710ad1047a30fd9a73899901f7a6950c5a7a72e3ba5c024c0849d0` |
| OpenFold3 | 0.5.0 |
| PyTorch / CUDA | 2.10.0 NVIDIA 25.11 build / CUDA 13.0 |
| Conversion / validation environment | Biotite 1.7.1, MDAnalysis 2.11.0, RDKit 2026.9.1 |

## Input and artifact identities

| Item | SHA-256 |
| --- | --- |
| Public challenge CSV as downloaded | `084ee90d1ee3444af287719fceb212572160684d5db219ae5eacdc2e0b7b165d` |
| Two-chain reference query (`examples/zikv_ns2b_ns3.json`) | `36c2c752e0c88666a93d36bb01795231c113d828a3c191ddb8378b68c8c6aeb4` |
| Generated 400-query JSON | `0e8673111c70bdbab1d77a94e9b85e9461974d0beb2d32172cd8a87b6303a02f` |
| Saved `query_msa.json` | `5b28a46b4df35fb911920023288067f338b7a082e850fe0d4bd5a9173075a0eb` |
| OpenBind-0 checkpoint | `bd43301c011d5f87580d3e8b548658869433e4488399feb03035ba248f8e29e4` |
| Validated submission ZIP | `9572ec2a47da5c7f6fe7fc084158dacb08db33a0bf095ee0d0ea6cbdfbe4b81e` |

The checkpoint file was 2,287,872,989 bytes. The public ligand CSV was downloaded from the [OpenBind Blind Challenge 1 dataset](https://huggingface.co/datasets/openadmet/openbind-blind-challenge-1). The generated files and ZIP are local artifacts excluded from Git.

## Prediction settings and outcome

- Target: two protein chains, A (46 residues) and B (168 residues), plus one ligand from each public SMILES row.
- MSAs: two saved main `.npz` alignments and two saved paired `.npz` alignments generated with OpenFold3's `align-msa-server` and reused under `/msas`.
- Model: OpenBind-0 checkpoint supplied through `--inference-ckpt-path`.
- Inference: `--use-msa-server false`, `--use-templates false`, `--num-model-seeds 1`, `--num-diffusion-samples 1`.
- GPU: one device, using the local `openbind-dgx-spark:0.5.0` container.
- Run summary: **400 processed, 400 successful, 0 failed**.
- Files: 400 model CIFs and 400 aggregated-confidence JSON files.
- First CIF saved: 2026-10-29 15:42:01 PDT. Last CIF saved: 2026-10-29 17:22:42 PDT. Span: 100.7 minutes.
- Per-query recorded runtime: median 15.1 seconds, range 13.6–20.8 seconds.

The first-to-last span is not the full command wall time; it excludes startup before the first saved structure and cleanup after the last. The run summary and timing data are retained locally in `workspace/outputs/ligand-screen/`.

## Submission preparation and validation

- Biotite converted 400 CIFs into 400 `{id}.pdb` files and changed the ligand residue name from `LIG0` to `LIG`.
- The resulting ZIP contained exactly 400 PDB files at its root and passed ZIP integrity testing.
- The [challenge tutorial validator](https://github.com/OpenADMET/OpenBind-Challenge-1-Tutorial/blob/main/validation/structure_validation.py) returned `valid: true` with **zero errors** when given all expected IDs and SMILES. Its checks cover file count, names, ligand residue, chain count, and ligand connectivity.
- The ZIP size was 11,400,768 bytes. The local validation report is `workspace/outputs/ligand-screen-validation.json`.

This record does not claim an upload, acceptance by the challenge portal, or a leaderboard score. The local validation demonstrates submission-format compatibility, not structural accuracy.
