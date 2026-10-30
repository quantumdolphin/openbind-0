# The ARM64 source manifest is verified by pull_ngc_base.py against
# sha256:4a85d8cf6fb3a943280960b8948cf4e9b6eca77b4414c68c9b2c7bb863f79b70.
FROM nvcr.io/nvidia/pytorch:25.11-py3

RUN python3 -m pip install --no-cache-dir \
       'openfold3==0.5.0' 'pynvml' 'biotite==1.7.1' 'pytorch-lightning==2.6.1' \
    && python3 -m pip check \
    && python3 -c 'import importlib.metadata, torch; assert importlib.metadata.version("openfold3") == "0.5.0"; assert torch.version.cuda is not None; print("OpenFold3", importlib.metadata.version("openfold3"), "PyTorch", torch.__version__, "CUDA", torch.version.cuda)'

RUN python3 -c 'import biotite.setup_ccd; from openfold3.setup_openfold import setup_biotite_ccd; setup_biotite_ccd(ccd_path=biotite.setup_ccd.OUTPUT_CCD, force_download=False)'

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       libx11-6 libxext6 libxrender1

WORKDIR /workspace
