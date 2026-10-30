# Reproduce the OpenBind-0 challenge run

Run commands from this repository's root directory. The tested hardware was an NVIDIA DGX Spark (ARM64, GB10, driver 580.142) with Docker GPU access. The image and data downloads need network access; prediction uses the local GPU.

## 1. Build the image and verify the checkpoint

```bash
docker build --progress=plain -t openbind-dgx-spark:0.5.0 .
python3 download_weights.py
```

The image installs OpenFold3 0.5.0 on `nvcr.io/nvidia/pytorch:25.11-py3`. The weight downloader verifies the expected file size and SHA-256. If the NVIDIA base image is difficult to pull, `python3 pull_ngc_base.py` provides a resumable ARM64 download before building. Existing verified weights and image can be reused; there is no need to redownload them for each run.

## 2. Get the public ligand list

```bash
mkdir -p workspace/inputs
curl -fL https://huggingface.co/datasets/openadmet/openbind-blind-challenge-1/resolve/main/openbind-blind-challenge-1-TEST-BLINDED.csv \
  -o workspace/inputs/openbind-blind-challenge-1-TEST-BLINDED.csv
```

The dataset has `Molecule_Name` and `SMILES` columns and 400 rows. `build_ligand_screen.py` also accepts a CSV with `id` and `smiles` columns. The two protein sequences are recorded in [`examples/zikv_ns2b_ns3.json`](../examples/zikv_ns2b_ns3.json).

## 3. Generate and save the two-chain MSA

```bash
bash generate_msa.sh examples/zikv_ns2b_ns3.json workspace/msas/zikv-ns2b-ns3
```

This calls OpenFold3's `align-msa-server` command. It contacts ColabFold once and saves two main MSAs, two paired MSAs, mapping files, and `query_msa.json`. If that directory already contains a valid `query_msa.json`, the script validates and reuses it.

## 4. Build and check 400 queries

```bash
python3 build_ligand_screen.py examples/zikv_ns2b_ns3.json \
  workspace/inputs/openbind-blind-challenge-1-TEST-BLINDED.csv \
  workspace/inputs/ligand-screen.json

bash predict.sh --check --msa-dir workspace/msas/zikv-ns2b-ns3 \
  workspace/inputs/ligand-screen.json
```

The dry run checks the image, checkpoint hash, JSON syntax, saved files, and the protein chain IDs and sequences for every ligand query.

## 5. Predict with the saved MSAs

```bash
bash predict.sh --msa-dir workspace/msas/zikv-ns2b-ns3 \
  workspace/inputs/ligand-screen.json workspace/outputs/ligand-screen
```

This runs all 400 queries on the GPU with one model seed and one diffusion sample per query. It does not query the MSA server again or use templates. `workspace/outputs/ligand-screen/summary.txt` records the query result counts. Use a new output directory for a different run; OpenFold3's `skip_existing` setting is false in this workflow.

## 6. Convert CIFs to the challenge PDB ZIP

```bash
python3 -m venv workspace/.venv-submission
workspace/.venv-submission/bin/python -m pip install -r requirements-submission.txt

workspace/.venv-submission/bin/python convert_openfold_cif_to_pdb.py \
  workspace/outputs/ligand-screen \
  workspace/outputs/ligand-screen-pdb \
  --ligands-csv workspace/inputs/openbind-blind-challenge-1-TEST-BLINDED.csv \
  --zip workspace/outputs/ligand-screen-submission.zip
```

The converter expects one CIF per ID and refuses missing, duplicate, or extra IDs. It renames the ligand residue `LIG0` to `LIG`, writes 400 `{id}.pdb` files, and packages them at the root of the ZIP. Choose fresh output paths when rerunning conversion.

## 7. Validate against the challenge tutorial

Use the [challenge tutorial's validator](https://github.com/OpenADMET/OpenBind-Challenge-1-Tutorial/blob/main/validation/structure_validation.py), which checks the ZIP, file names, ligand residue, chain count, and ligand connectivity against the expected SMILES. For a fresh checkout:

```bash
git clone https://github.com/OpenADMET/OpenBind-Challenge-1-Tutorial.git workspace/challenge-tutorial
PYTHONPATH=workspace/challenge-tutorial workspace/.venv-submission/bin/python - <<'PY'
import csv
from pathlib import Path
from validation.structure_validation import validate_structure_submission

with Path('workspace/inputs/openbind-blind-challenge-1-TEST-BLINDED.csv').open(newline='') as stream:
    smiles = {row['Molecule_Name']: row['SMILES'] for row in csv.DictReader(stream)}
valid, errors = validate_structure_submission(
    'workspace/outputs/ligand-screen-submission.zip',
    expected_ids=set(smiles),
    expected_ligand_smiles=smiles,
)
print('Valid:', valid, 'Errors:', len(errors))
for error in errors[:20]:
    print(error)
raise SystemExit(0 if valid else 1)
PY
```

This verifies submission structure, not experimental pose accuracy. The specific successful run is recorded in [RUN_RECORD.md](RUN_RECORD.md). No weights, MSAs, predictions, or ZIP are stored in this Git repository.
