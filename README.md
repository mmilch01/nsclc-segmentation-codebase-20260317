# NSCLC Tumor Segmentation XNAT Container

## 1. Overview

This repository contains code for an XNAT container runtime that wraps the NSCLC lesion segmenter. It detects all structural chest CT scans in a session, and for each scan runs the segmenter. It then converts the segmentation into RTSTRUCT and uploads it to a session scan. All processing outputs and logs are uploaded to a session resource.

## 2. Lesion Segmenter

The lesion segmenter is embedded in the container. Reference to the segmenter <pending>.

The segmenter loads a chest CT scan, standardizes its spacing and slice shape, and crops or pads it to the model input size. It then segments the lung region so inference is focused on lung tissue rather than the full chest. The CT values are windowed and rescaled into the intensity range expected by the model. A trained NSCLC lesion model is applied slice by slice to produce lesion probability maps. These maps are thresholded into a binary mask, cleaned by keeping the dominant connected 3D lesion region, and then mapped back into the original CT geometry.

## 3. Building the Docker Image

**Prerequisites:** [micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html), [pymipl](https://github.com/mmilch01/pymipl.git), lesion segmenter codebase and this repository.

The build steps are:

1. Clone this runtime and `pymipl` repositories.
2. Obtain the NSCLC segmenter repository from the developer <reference pending>
3. Build the Python environment for the segmenter:
```bash
mkdir -p /opt/user/env_repo
micromamba create -p /opt/packages/user/env_repo --rc-file /dev/null --no-env -c conda-forge -r requirements.txt python=3.10
micromamba activate -p /opt/packages/user/env_repo
cd <segmenter_source_repo>
pip install -r requirements.txt
```
4. Create a Docker build config file, using `nsclc-segmentation-codebase-20260317-example.conf` in this repository as a model.
5. Run:
```bash
{PYMIPL_DIR}/build_deploy_custom_image.sh
```

The build config should identify the local micromamba environment folder (/opt/packages/user/env_repo in this example), the segmentation algorithm source directory, and this repo runtime repository so they can be copied into the Docker image.

## 4. Running Locally
This container can run on a local machine. For that, a directory containing XNAT-like session hierarchy should exist in the data directory, i.e. SCANS/<scan_no>/DICOM/<dicom_files>.
```bash
cd <data_directory>
docker run --rm -t -i -u $(id -u ${USER}):$(id -g ${USER}) -v <data_directory>:/input <image_name>:latest micromamba run -n base python /opt/packages/user/runtime_repo/entrypoint.py --project NSCLC_RADIOMICS --session <XNAT session label> --host <XNAT host> --user <XNAT user> --pass <XNAT password>
```

`--host`, `--user`, and `--pass` fall back to the environment variables `XNAT_HOST`, `XNAT_USER`, and `XNAT_PASS` respectively if not supplied on the command line.

## 5. Running in XNAT

1. In the XNAT Container Service, register the command using `command.json`, and activate the command globally and for the target project.
2. From an individual session, run the **"NSCLC Tumor segmentation - Gevaert Lab"** command.

## 6. Outputs

The segmentation scan in RTSS format is saved in the same session under scan ID `100<structural scan ID>`.
The session resource "nsclc-segmentation-codebase-20260317" structure output is:

```text
.
|-- batch_<date-time>.sh
|-- <Subject>
|   `-- <Experiment>
|       `-- <Structural Scan>
|           |-- ct_struct.nii
|           |-- lesion_mask.nii.gz
`-- <Project ID>
    |-- jobs
    |   `-- nsclc-segmentation-codebase-20260317_LUNG1-093_09-18-2008-StudyID-NA-69331_<job-id>
    |       `-- job.yaml
    |-- project_dir_structure.json
    |-- scans.csv
    `-- xnat_structure.json
```

Key outputs include:

- `lesion_mask.nii.gz`: lesion mask in NIFTI format.
- `ct_struct.nii`: converted structural CT image.
- `scans.csv`: discovered structural scan list.
- `project_dir_structure.json` and `xnat_structure.json`: XNAT/project structure metadata used by the workflow.
- `jobs/.../job.yaml`: generated per-scan workflow job definition.
- `batch_*.sh`: generated batch script executed by the entrypoint.
