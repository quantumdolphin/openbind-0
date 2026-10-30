# Learning notes: from OpenFold3 image to challenge ZIP

These notes explain the decisions and small surprises in this run so I can understand it later without reconstructing the terminal session.

## 1. Three different things: image, container, and weights

The `openbind-dgx-spark:0.5.0` **image** is a stored software environment. Its `Dockerfile` starts from NVIDIA's ARM64 PyTorch 25.11 image and installs OpenFold3 0.5.0. A **container** is one running copy of that image. `predict.sh` starts a fresh container with `docker run --rm`, then Docker removes the container when the prediction command finishes.

The OpenBind-0 **checkpoint** is the trained model parameters, not another image. The 2.3 GB file remains in the host's `weights/` directory and is mounted read-only into the container at `/weights`. `run_openfold predict` receives its path through `--inference-ckpt-path`. Rebuilding the image does not duplicate the checkpoint. The installed `nvcr.io/nim/openfold/openfold3:latest` NIM image is a separate server product and was not used here.

## 2. Why the MSA was saved once

The target has two protein chains, A and B. Each ligand changes, but those protein sequences do not. OpenFold3 can use **main MSAs** for each chain and **paired MSAs** for the two-chain complex. `generate_msa.sh` queried the ColabFold server once and saved the main and paired `.npz` files under `workspace/msas/zikv-ns2b-ns3/`.

The generated `query_msa.json` records paths beginning with `/msas`. During every later prediction, `predict.sh --msa-dir` mounts that same host folder at `/msas`, so the paths remain valid inside the container. `prepare_msa_queries.py` compares both protein chain IDs and sequences against the reference before attaching the saved paths to every ligand query. The inference command keeps `--use-msa-server false`; this avoids querying ColabFold again.

One implementation detail mattered: OpenFold3's generated `query_msa.json` writes the molecule type as uppercase `PROTEIN`, whereas the input examples use lowercase `protein`. The validator now accepts both. The first alignment generation succeeded at the server but failed this local validation; fixing the case handling allowed the saved files to be reused without downloading again.

## 3. Why 15 seconds per query meant roughly 101 minutes

`build_ligand_screen.py` put 400 named complexes in one query JSON. OpenFold3 loaded the model once, then predicted the 400 complexes sequentially on one GPU. The median per-query runtime in this run was 15.1 seconds. Multiplying by 400 gives about 6,040 seconds, or 101 minutes, matching the observed 100.7 minutes from the first saved structure to the last. Saving the MSA avoids repeated alignment searches; it does not avoid the separate model calculation for each ligand.

The 400/400 success count in `summary.txt` means OpenFold3 produced outputs without reported query failures. It does **not** mean all 400 poses are experimentally correct.

## 4. Prediction files are different from submission files

OpenFold3 wrote one `.cif` structure and confidence records for each ligand. The challenge asks for a ZIP of 400 PDB files named after the ligand IDs, with exactly one ligand residue named `LIG`. The generated CIFs used `LIG0`. The conversion script adapts the challenge tutorial's Biotite helper to traverse OpenFold3's nested output directories, rename `LIG0` to `LIG`, write `{id}.pdb`, and create a ZIP.

The challenge tutorial's validator accepted the ZIP with 400 expected IDs and zero errors, including its ligand-connectivity check. That validates the **submission format and parseability**, not pose quality. A leaderboard result would be separate evidence about accuracy.

## 5. What to remember before another run

- Keep large weights, MSAs, predictions, and the local Python environment out of Git. `.gitignore` excludes them.
- Use `bash predict.sh --check --msa-dir ... QUERY_JSON` before a long batch. A protein sequence or chain-ID mismatch stops reuse of the saved MSA.
- A source JSON can live outside this folder; the scripts resolve and mount its absolute path. Relative paths are interpreted from the shell's current directory.
- The current prediction script uses one model seed, one diffusion sample, saved MSAs, and no templates. A higher-sampling or template-assisted experiment is a **new method** and needs its own record and output directory.
- `convert_openfold_cif_to_pdb.py` refuses an existing destination so a rerun does not silently overwrite the earlier submission.
- For the challenge's final leaderboard, keep a public method report or repository link with the submission. Disclose any proprietary training data accurately; this workflow itself did no extra training.

See [the reproducibility guide](REPRODUCE.md), [method report](SUBMISSION_METHODS.md), and [run record](RUN_RECORD.md) for commands and evidence.
