# OpenBind Blind Challenge 1: methods report draft

**Status:** Local prediction and submission-format validation complete. This is a draft methods report; it does not claim a portal upload or leaderboard result.

## Objective and inputs

We predicted one complex for each of the 400 blinded small molecules in the [OpenBind Blind Challenge 1 public dataset](https://huggingface.co/datasets/openadmet/openbind-blind-challenge-1). Each complex contained the same two-chain Zika virus NS2B–NS3 protease construct: chain A (46 amino acids) and chain B (168 amino acids), as provided in the [challenge tutorial](https://github.com/OpenADMET/OpenBind-Challenge-1-Tutorial). Ligands were specified by the dataset's SMILES strings. The exact protein input is in [`examples/zikv_ns2b_ns3.json`](../examples/zikv_ns2b_ns3.json).

## Model and environment

We used [OpenFold3 v0.5.0](https://github.com/aqlaboratory/openfold-3/releases/tag/v0.5.0) with the public OpenBind-0 checkpoint `of3-ob-2025-06-30-174k.pt`. The code ran on one NVIDIA DGX Spark GB10 GPU in a local ARM64 container built from NVIDIA PyTorch 25.11. The checkpoint was mounted into the container; it was not embedded in the image. We did not fine-tune or otherwise train the model as part of this workflow.

## MSA and inference

OpenFold3's ColabFold MSA-server command generated main alignments for each protein chain and paired alignments for their complex once. The resulting `.npz` files were saved locally and reused for all 400 ligand queries. Each query was checked against the reference protein chain IDs and sequences before the saved alignments were attached.

The 400 queries were submitted as one OpenFold3 prediction job using one model seed and one diffusion sample per query. Online MSA generation and templates were disabled during prediction because the saved alignments were supplied directly. No template or pocket constraint was used. OpenFold3 produced one CIF structure and associated confidence records per ligand.

## Submission preparation and checks

The CIFs were converted to PDB using Biotite 1.7.1, following the approach in the challenge tutorial notebook. The OpenFold3 ligand residue label `LIG0` was changed to the required `LIG`. Each output was named `{Molecule_Name}.pdb` and the 400 PDBs were packaged in one ZIP.

The challenge tutorial's `validate_structure_submission()` accepted the ZIP with all 400 expected IDs and zero errors when supplied with the expected ligand SMILES. This confirms the local format, residue, chain-count, and connectivity checks passed. OpenFold3's run summary reported 400 successful queries and zero failures. Neither result measures agreement with the withheld experimental structures or predicts a challenge score.

## Reproducibility and disclosure notes

The scripts, exact command sequence, model identity, hashes, and run timings are in this repository's [reproducibility guide](REPRODUCE.md) and [run record](RUN_RECORD.md). The input compound list, OpenFold3 software, and OpenBind-0 parameters came from public sources. No additional training was performed in this workflow. The submitter should independently confirm any proprietary-data disclosure and add the public repository URL after publication.
