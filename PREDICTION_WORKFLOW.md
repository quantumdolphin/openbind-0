# How an OpenBind-0 prediction runs

This guide explains what happens when you run [`predict.sh`](predict.sh) in this folder. The short version is: Docker starts OpenFold3, OpenFold3 loads the OpenBind-0 weights, and the predicted structure is saved on your computer.

## Image, container, and checkpoint

- **Docker image:** `openbind-dgx-spark:0.5.0` is the installed software package. This folder's [`Dockerfile`](Dockerfile) builds it from NVIDIA's ARM64 PyTorch image and installs OpenFold3 0.5.0.
- **Container:** A temporary running copy of that image. Each invocation of `predict.sh` creates a new container.
- **Checkpoint:** `weights/of3-ob-2025-06-30-174k.pt` contains the OpenBind-0 model parameters. It stays outside the image and is made available to the container when it runs.

The prediction path is:

```text
query JSON + OpenBind-0 checkpoint
              |
              v
container started from openbind-dgx-spark:0.5.0
              |
              v
OpenFold3 runs the prediction with GPU access
              |
              v
workspace/outputs/ on this computer
```

## Run an example

From this folder, run:

```bash
bash predict.sh examples/ubiquitin.json
```

To check the input, checkpoint, Docker, and image without starting a prediction:

```bash
bash predict.sh --check examples/ubiquitin.json
```

If your Bash alias is loaded, the equivalent command is:

```bash
openbind-predict examples/ubiquitin.json
```

You can choose an output folder with a second argument:

```bash
bash predict.sh examples/blind_challenge_001.json workspace/outputs/my-prediction
```

The input JSON describes the molecules to predict. [`examples/ubiquitin.json`](examples/ubiquitin.json) contains one protein chain. [`examples/blind_challenge_001.json`](examples/blind_challenge_001.json) shows two protein chains and a ligand specified by SMILES. Copy one of these files and replace its sequences or ligand SMILES to predict your own target.

## Reuse an MSA for a two-chain complex

The plain `predict.sh` command above uses a dummy, single-sequence MSA because it disables the online MSA server. For a two-chain protein complex screened against many ligands, generate and save the protein alignments once:

```bash
bash generate_msa.sh examples/zikv_ns2b_ns3.json workspace/msas/my-target
```

Use a reference query with your actual two protein sequences and chain IDs. `generate_msa.sh` contacts the ColabFold MSA server, so this step needs network access and can take time. It saves OpenFold3-formatted main MSAs for both protein chains, paired MSAs for a heteromer when generated, and `query_msa.json` in `workspace/msas/my-target/`. The `/msas` paths in that JSON remain valid because later prediction containers mount the saved folder at the same location.

Then reuse those alignments for a query JSON containing the same two protein chains and one or more ligands:

```bash
bash predict.sh --msa-dir workspace/msas/my-target \
  examples/blind_challenge_001.json \
  workspace/outputs/with-saved-msa
```

The script writes `query_with_msa.json` in the output folder. This is a copy of your input with the saved MSA paths attached to the matching protein chains. It checks every query's protein sequences and chain IDs against the reference; a mismatch stops the run. The ligand can differ between queries. To check a 400-ligand input without running inference:

```bash
bash predict.sh --check --msa-dir workspace/msas/my-target workspace/inputs/ligand-screen.json
```

To create that input from a ligand table, save a CSV with `id,smiles` columns, for example:

```csv
id,smiles
ligand_001,CCO
ligand_002,CCN
```

Then build and check the batch:

```bash
python3 build_ligand_screen.py examples/zikv_ns2b_ns3.json \
  workspace/inputs/ligands.csv workspace/inputs/ligand-screen.json
bash predict.sh --check --msa-dir workspace/msas/my-target workspace/inputs/ligand-screen.json
```

`ligand-screen.json` will contain one named query per CSV row, each with the same two protein chains and its own ligand. One batch run loads the model once and lets OpenFold3 reuse the same saved alignments:

```bash
bash predict.sh --msa-dir workspace/msas/my-target \
  workspace/inputs/ligand-screen.json workspace/outputs/ligand-screen
```

You can also run separate query files with the same `--msa-dir`, but each invocation starts a new container and loads the model again. Keep `workspace/msas/my-target/` intact while you need these alignments. A 400-ligand batch may take a long time and produce substantial output, so try a small subset first.

The saved MSA improves the information available to the model, but it does not remove the per-ligand prediction work. The MSA is reusable only while the relevant protein sequences remain the same. See the [OpenFold3 v0.5.0 inference guide](https://github.com/aqlaboratory/openfold-3/blob/v0.5.0/docs/source/inference.md) for the upstream precomputed-MSA workflow.

## Convert predictions for challenge submission

The challenge requires a ZIP containing exactly 400 PDB files named `<id>.pdb`, each with one ligand residue named `LIG`. OpenFold3 writes CIF files and labels its ligand `LIG0`. [`convert_openfold_cif_to_pdb.py`](convert_openfold_cif_to_pdb.py) adapts the Biotite conversion helper in the challenge tutorial notebook: it reads each CIF, renames `LIG0` to `LIG`, writes one PDB per query, and packages the PDBs into a ZIP. It refuses missing or duplicate query IDs and does not overwrite existing output paths.

Install the conversion and validation packages in a local environment if needed:

```bash
python3 -m venv workspace/.venv-submission
workspace/.venv-submission/bin/python -m pip install -r requirements-submission.txt
```

Convert the completed 400-query run:

```bash
workspace/.venv-submission/bin/python convert_openfold_cif_to_pdb.py \
  workspace/outputs/ligand-screen \
  workspace/outputs/ligand-screen-pdb \
  --ligands-csv workspace/inputs/ligands.csv \
  --zip workspace/outputs/ligand-screen-submission.zip
```

Run the challenge tutorial's `validate_structure_submission()` on the ZIP, supplying the expected ligand IDs and SMILES from `workspace/inputs/ligands.csv`. The validation checks names, `LIG` residue count, chain count, and ligand connectivity. Validation is separate from conversion so a PDB file is never treated as submission-ready solely because it was written successfully.

## What `predict.sh` does

1. **Check the files.** It checks that the query JSON exists and is valid JSON, then verifies the OpenBind-0 checkpoint's SHA-256. It also checks that Docker is available and that the local image exists. With `--msa-dir`, it checks every query against the saved two-chain alignments. It stops with a message if a check fails. Use `--check` to run only these checks.

2. **Prepare folders.** It creates `workspace/cache/` and the output folder. If you do not supply an output folder, it creates a timestamped folder under `workspace/outputs/`, so an earlier run's results are not overwritten.

3. **Start a container from the OpenFold3 image.** It calls `docker run` with `openbind-dgx-spark:0.5.0`. Docker creates a fresh container from this local image, gives it access to the NVIDIA GPU, and runs it as your user ID so output files belong to you. This image contains the OpenFold3 software; the OpenBind-0 checkpoint is supplied in the next step.

4. **Make files available inside the container.** Docker connects host paths to paths inside the container:

   | On your computer | Inside the container | Purpose |
   | --- | --- | --- |
   | The query JSON you passed | `/input/query.json` | Prediction input; mounted read-only |
   | `weights/` | `/weights` | OpenBind-0 checkpoint; mounted read-only |
   | `workspace/cache/` | `/workspace/cache` | Reusable cache |
   | The chosen output folder | `/output` | Predictions and run records |

   These are mounts: the checkpoint is not copied into the Docker image, and files written under `/output` appear in your chosen host output folder.

5. **Run OpenFold3 with OpenBind-0.** Inside the container, `run_openfold predict` reads `/input/query.json` and uses `--inference-ckpt-path /weights/of3-ob-2025-06-30-174k.pt`. The script requests one model seed and one diffusion sample. It disables the online MSA server and templates. Those settings are useful for a quick run; they may affect prediction quality for a real target. Change the final `run_openfold predict` options in [`predict.sh`](predict.sh) if you need different settings.

6. **Keep the results.** OpenFold3 writes a predicted structure (`*_model.cif`), confidence files, configuration files, and a `summary.txt` under the output folder. The script prints that folder's path and the summary when the command finishes. Docker's `--rm` option removes the finished container. The Docker image, checkpoint, cache, and output files remain available for later runs.

## Which OpenFold3 image is used?

`docker images` may also show `nvcr.io/nim/openfold/openfold3:latest`. That is a separate NVIDIA OpenFold3 NIM server image. This folder's `predict.sh` does **not** use it. The script runs `openbind-dgx-spark:0.5.0`, which this folder builds specifically for command-line OpenBind-0 predictions.
