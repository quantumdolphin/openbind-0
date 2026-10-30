# OpenBind-0 on DGX Spark

This repository records a complete OpenBind Blind Challenge 1 structure-prediction workflow on an NVIDIA DGX Spark. It builds an ARM64 OpenFold3 0.5.0 image, saves MSAs for the two-chain Zika virus NS2B–NS3 protease, predicts complexes for 400 public challenge ligands, and converts the resulting CIF structures into the challenge's PDB ZIP format.

The recorded run produced 400 structures from 400 queries. The challenge tutorial's local submission validator accepted the ZIP with zero format or ligand-connectivity errors. **These checks do not establish pose accuracy or a leaderboard score.** See [the run record](docs/RUN_RECORD.md) for the exact environment, settings, timings, and artifact hashes.

## Start here

- [Learning notes](docs/LEARNING_NOTES.md) explain the image, container, checkpoint, MSA, batching, and submission concepts.
- [Reproduce the workflow](docs/REPRODUCE.md) gives the commands in order.
- [Prediction workflow](PREDICTION_WORKFLOW.md) explains what each script does.
- [Submission methods report](docs/SUBMISSION_METHODS.md) is a draft methodology summary for the challenge portal.
- [Run record](docs/RUN_RECORD.md) captures the 2026-10-29 run and its validation evidence.

## Quick path

Run these commands from the repository root on a DGX Spark with Docker and the NVIDIA container runtime. The model weights, alignments, and prediction outputs are downloaded or generated locally and are excluded from Git.

```bash
# Build OpenFold3 0.5.0 on the NVIDIA ARM64 PyTorch base and get OpenBind-0 weights.
docker build --progress=plain -t openbind-dgx-spark:0.5.0 .
python3 download_weights.py

# Download the public challenge ligand table.
mkdir -p workspace/inputs
curl -fL https://huggingface.co/datasets/openadmet/openbind-blind-challenge-1/resolve/main/openbind-blind-challenge-1-TEST-BLINDED.csv \
  -o workspace/inputs/openbind-blind-challenge-1-TEST-BLINDED.csv

# Generate the target's main and paired MSAs once.
bash generate_msa.sh examples/zikv_ns2b_ns3.json workspace/msas/zikv-ns2b-ns3

# Build and check one JSON containing all 400 protein-ligand queries.
python3 build_ligand_screen.py examples/zikv_ns2b_ns3.json \
  workspace/inputs/openbind-blind-challenge-1-TEST-BLINDED.csv \
  workspace/inputs/ligand-screen.json
bash predict.sh --check --msa-dir workspace/msas/zikv-ns2b-ns3 \
  workspace/inputs/ligand-screen.json

# Predict using the saved MSAs.
bash predict.sh --msa-dir workspace/msas/zikv-ns2b-ns3 \
  workspace/inputs/ligand-screen.json workspace/outputs/ligand-screen
```

See [Reproduce the workflow](docs/REPRODUCE.md) for conversion, challenge validation, and what to do if the image or downloads are already present.

## Images and model weights

[`Dockerfile`](Dockerfile) builds `openbind-dgx-spark:0.5.0` from `nvcr.io/nvidia/pytorch:25.11-py3` and installs OpenFold3 0.5.0. [`predict.sh`](predict.sh) starts a temporary GPU container from this image. The OpenBind-0 checkpoint `of3-ob-2025-06-30-174k.pt` stays in `weights/` on the host and is mounted read-only for inference. The separate NVIDIA OpenFold3 NIM image is not used by these scripts.

## Repository contents

| File | Purpose |
| --- | --- |
| [`generate_msa.sh`](generate_msa.sh) | Fetch and save main and paired alignments for the two-chain reference complex. |
| [`build_ligand_screen.py`](build_ligand_screen.py) | Turn the public CSV into an OpenFold3 JSON with one query per ligand. |
| [`prepare_msa_queries.py`](prepare_msa_queries.py) | Verify both protein chains match the saved MSAs and attach alignment paths. |
| [`predict.sh`](predict.sh) | Check inputs and run OpenFold3 with the OpenBind-0 checkpoint on the GPU. |
| [`convert_openfold_cif_to_pdb.py`](convert_openfold_cif_to_pdb.py) | Convert CIFs to named PDBs with `LIG` residue names and package a ZIP. |
| [`download_weights.py`](download_weights.py) | Download and verify the OpenBind-0 checkpoint. |
| [`pull_ngc_base.py`](pull_ngc_base.py) | Optional resumable pull of the NVIDIA ARM64 base image. |

The 2.3 GB checkpoint, downloaded container layers, virtual environment, MSAs, 400 predictions, and submission ZIP are intentionally excluded by [`.gitignore`](.gitignore). The reproducibility record includes hashes and counts without publishing these large files.

## Sources and license

The workflow uses [OpenFold3 v0.5.0](https://github.com/aqlaboratory/openfold-3/releases/tag/v0.5.0), the [OpenBind Blind Challenge 1 dataset](https://huggingface.co/datasets/openadmet/openbind-blind-challenge-1), and the [challenge tutorial and validator](https://github.com/OpenADMET/OpenBind-Challenge-1-Tutorial). The CIF-to-PDB conversion approach was adapted from the tutorial notebook. This repository's own scripts and documentation are released under the [MIT license](LICENSE).
