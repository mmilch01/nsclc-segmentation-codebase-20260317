import os
import sys
import json
import datetime
import argparse
import subprocess
import yaml
from pathlib import Path
# Library with XNAT Jupyter workflow Python and shell scripts.
pymipl_path = Path("/opt/packages/pymipl")
sys.path.append(str(pymipl_path))
sys.path.append(str(pymipl_path / "xnat_workflow"))

# dicom_sort is part of pymipl. It analyzes XNAT projects for structural scans
# and segmentations.
from dicom_sort import analyze_dir, reindex_to_structurals_and_segs
import workflow_adapters as wa


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build NSCLC segmentation workflow jobs from an XNAT project."
    )
    parser.add_argument("--project", required=True, help="XNAT project label.")
    parser.add_argument("--session", help="XNAT experiment/session label or ID. Required for experiment-level mounts.")
    parser.add_argument("--host", required=True, help="XNAT host URL.")
    parser.add_argument("--user", required=True, help="XNAT username.")
    parser.add_argument("--pass", dest="password", required=True, help="XNAT password.")
    return parser.parse_args()


def normalize_xnat_input(input_root, view_root, experiment):
    """Return a project-shaped input path for dicom_sort."""
    project_level_experiments = input_root / "experiments"
    experiment_level_scans = input_root / "SCANS"
    if project_level_experiments.is_dir(): return input_root / "experiments"
    if experiment_level_scans.is_dir():
        if not experiment: raise ValueError("Experiment-level /input detected, but --experiment was not provided.")
        experiment_dir = view_root / "experiments" / experiment
        experiment_dir.mkdir(parents=True, exist_ok=True)
        scans_link = experiment_dir / "SCANS"
        if scans_link.exists():
            if scans_link.resolve() != experiment_level_scans.resolve():
                raise ValueError(f"{scans_link} already exists and does not point to {experiment_level_scans}.")
        else:
            scans_link.symlink_to(experiment_level_scans, target_is_directory=True)
        return view_root / "experiments"
    raise ValueError("Unrecognized /input layout. Expected /input/experiments/... or /input/SCANS/...")


def main():
    args = parse_args()

    #set to True to regenerate project directory structure saved in local json file.
    rebuild_directory_structure=True
    
    # XNAT project label
    project=args.project
    
    # Persistent workspace root path
    root_dir=Path("/workdir/processing")
    root_dir.mkdir(parents=True, exist_ok=True)
    
    # Derived variable initializations
    local_workdir_path = root_dir / project
    xnat_project_path = normalize_xnat_input(Path("/input"), Path("/workdir/input"), args.session)
    directory_structure_file = local_workdir_path / "project_dir_structure.json"
    xnat_structure_file = local_workdir_path / "xnat_structure.json"
    scanlist_file = local_workdir_path / "scans.csv"

    # analyze_dir finds all structural scans and segmentations (DICOM RTSTRUCT
    # and DICOM Segmentation Object) in the project. The results are saved into a
    # JSON file for quick rerun.
    if rebuild_directory_structure:
        os.makedirs(os.path.dirname(directory_structure_file), exist_ok=True)
        d = analyze_dir(xnat_project_path, directory_structure_file)
    else:
        with open(directory_structure_file, 'r') as file:
            d = json.load(file)
    
    # This writes out a human-readable list of structural scans with segmentations
    # into a CSV file.
    subjects, scans = reindex_to_structurals_and_segs(
        d,
        xnat_structure_file,
        scanlist_file
    )
    print(f'Number of structural scans: {len(scans)}')

    if len(scans) == 0: raise ValueError("No structural scans with segmentations found in the project.")

    print('First scan: ', scans[0])
    env_type="jupyter"
    
    # This is the label of the session resource where generated job scripts, logs,
    # and output will be saved.
    workflow_id="nsclc-segmentation-codebase-20260317"
       
    # User micromamba environment repository.
    user_env_repo="/opt/packages/user/env_repo"
    
    # User source/resource directory.
    user_src_repo="/opt/packages/user/alg_repo"
    
    global_vars = wa.init_global_vars(
        env_type,
        project,
        workflow_id,
        g_user_env_repo=user_env_repo,
        g_user_src_repo=user_src_repo,
        g_input_mount_path=xnat_project_path,
        g_local_workdir_path=root_dir,
        g_pymipl_dir=pymipl_path
    )

    print(f'global vars:{global_vars}')

    wa.set_logger()

    for scan in scans:       
        # Whether to upload the generated job script bundle to the session resource.
        UpdateSessionResource=True
        
        #################################################################
        # Other initializations

        dt = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        n = 0
        xnat_interface = None
        num_sessions = len(scans)

        job = wa.populate_job_fields(env_type, global_vars, workflow_id, scan, scan_key="StructScan")
        job['job_struct_path'] = job['job_scan_context'] / scan['StructScan'] / 'DICOM'
        print (f"job variables: {job}")


        job_yaml = Path(__file__).with_name("main_job.yaml")

        with open(job_yaml, "r") as f:
            job_steps = yaml.safe_load(f)

        job['steps'] = job_steps.get("steps", job_steps)
    
        local_job_dir = local_workdir_path / 'jobs' / job['job_id']
        job_file_yaml = local_job_dir / 'job.yaml'
        local_job_dir.mkdir(parents=True, exist_ok=True)

        with open(job_file_yaml, "w") as f:
            yaml.safe_dump(wa.paths_to_str(job), f, sort_keys=False)

        batch_file = root_dir / f"batch_{dt}.sh"

        with open(batch_file, 'w') as f:
            f.write('#!/bin/bash\n')

        wa.workflow_to_batch(job, global_vars, batch_file)
        batch_file.chmod(0o755)
        print(f'Written {batch_file}')

        print(f'Running {batch_file}')
        result = subprocess.run(["bash", str(batch_file)], check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"Batch file failed with exit code {result.returncode}: {batch_file}"
            )
        print(f'Completed {batch_file}')

        if UpdateSessionResource:
            if xnat_interface is None:
                xnat_interface = wa.pyxnat.Interface(
                    server=args.host,
                    user=args.user,
                    password=args.password,
                )
                xnat_interface.select.project(project)

            print('Sending job bundle to XNAT resource')
            res1 = wa.sync_resource_xnat(
                local_job_dir,
                workflow_id,
                project,
                subject=job['job_subject'],
                experiment=job['job_exp_label'],
                level="experiment",
                XNAT_HOST=args.host,
                xnat_interface=xnat_interface,
                create_hierarchy=True,
            )
            if res1 != 0:
                raise ConnectionError(
                    "Uploading job configuration to XNAT failed"
                )

if __name__ == "__main__":
    main()
