# NSCLC Tumor Segmentation XNAT Container

## 1. Overview

This XNAT container wraps the NSCLC lesion segmenter. It detects all structural chest CT scans in a session, and for each scan runs the segmenter. It then converts the segmentation into RTSTRUCT and uploads it to a session scan. All processing outputs and logs are uploaded to a session resource.

## 2. Lesion Segmenter

The lesion segmenter is embedded in the container. Reference to the segmenter GitHub repository is pending.

The segmenter loads a chest CT scan, standardizes its spacing and slice shape, and crops or pads it to the model input size. It then segments the lung region so inference is focused on lung tissue rather than the full chest. The CT values are windowed and rescaled into the intensity range expected by the model. A trained NSCLC lesion model is applied slice by slice to produce lesion probability maps. These maps are thresholded into a binary mask, cleaned by keeping the dominant connected 3D lesion region, and then mapped back into the original CT geometry.

## 3. Building the Docker Image

**Prerequisites:** [pymipl](https://github.com/mmilch01/pymipl.git)), lesion segmenter codebase and this repository.

The build steps are:

1. Clone this runtime and `pymipl` repositories.
2. Obtain the NSCLC segmenter repository from the developer. Reference pending.
3. Configure the Docker build config file, using `nsclc-segmentation-codebase-20260317-example.conf` in this repository as a model.
4. Run:
```bash
{PYMIPL_DIR}/build_deploy_custom_image.sh
```

The build config should identify the local micromamba environment folder, the segmentation algorithm source directory, and this runtime repository so they can be copied into the Docker image.

## 4. Running Locally

> TODO: show 'docker run' command rather than how this is run inside the container.

```bash
micromamba run -n base python /opt/packages/user/runtime_repo/entrypoint.py \
    --project <XNAT_PROJECT> \
    --session <XNAT_SESSION> \
    [--host <XNAT_HOST>] \
    [--user <XNAT_USER>] \
    [--pass <XNAT_PASS>]
```

`--host`, `--user`, and `--pass` fall back to the environment variables `XNAT_HOST`, `XNAT_USER`, and `XNAT_PASS` respectively if not supplied on the command line.


## 5. Running in XNAT

1. In the XNAT Container Service, register the command using `command.json` from this repository.
2. From an individual session, run the **"NSCLC Tumor segmentation - Gevaert Lab"** command.

## 6. Outputs

The session resource structure is:

```text
.
|-- batch_20260618_1522.sh
|-- LUNG1-093
|   `-- 09-18-2008-StudyID-NA-69331
|       `-- 0
|           |-- ct_struct.nii
|           |-- DICOM
|           |   `-- input_image.nii.gz
|           |-- lesion_mask.nii.gz
|           `-- secondary
|               `-- lesion_mask_rtss.dcm
`-- NSCLC_RADIOMICS
    |-- jobs
    |   `-- nsclc-segmentation-codebase-20260317_LUNG1-093_09-18-2008-StudyID-NA-69331_0
    |       `-- job.yaml
    |-- project_dir_structure.json
    |-- scans.csv
    `-- xnat_structure.json
```

The segmentation scan in RTSS format is also saved in the same session under scan ID `<structural scan ID>001`.

Key outputs include:

- `lesion_mask.nii.gz`: lesion mask in NIFTI format.
- `ct_struct.nii`: converted structural CT image.
- `scans.csv`: discovered structural scan list.
- `project_dir_structure.json` and `xnat_structure.json`: XNAT/project structure metadata used by the workflow.
- `jobs/.../job.yaml`: generated per-scan workflow job definition.
- `batch_*.sh`: generated batch script executed by the entrypoint.
