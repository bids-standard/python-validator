"""Runnable example for the filename validation module.

Two modes:

* No argument: build a small dataset in a temporary directory that contains one
  deliberately broken file per issue code, validate it, and print the findings.
  Every code the module can emit is demonstrated.
* With a path: validate your own dataset.

Usage
-----
    python docs/example_filename_issues.py                    # generated demo
    python docs/example_filename_issues.py /path/to/dataset   # your own data
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from bidsschematools.schema import load_schema

from bids_validator.filename_checks import collect_filename_issues
from bids_validator.issues import Severity
from bids_validator.types.files import FileTree

# Correctly named files. None of these produce a finding.
VALID_FILES = (
    'README',
    'sub-01/anat/sub-01_T1w.nii.gz',
    'sub-01/func/sub-01_task-rest_bold.nii.gz',
)

# One broken file per issue code, with the code each one is expected to raise.
BROKEN_FILES = {
    'sub-01/notes.txt': 'NOT_INCLUDED',
    'sub-01/anat/sub-01_T1w.txt': 'EXTENSION_MISMATCH',
    'sub-01/func/sub-01_bold.nii.gz': 'MISSING_REQUIRED_ENTITY',
    'sub-01/anat/sub-01_acq-_T1w.nii.gz': 'ENTITY_WITH_NO_LABEL',
    'sub-01/anat/sub-01_acq-a!b_T1w.nii.gz': 'INVALID_ENTITY_LABEL',
    'sub-01/anat/sub-01_dir-AP_T1w.nii.gz': 'ENTITY_NOT_IN_RULE',
    'sub-01/anat/acq-x_sub-01_T1w.nii.gz': 'FILENAME_MISMATCH',
    'sub-01/func/sub-01_T1w.nii.gz': 'DATATYPE_MISMATCH',
    'sub-02/anat/sub-01_T1w.nii.gz': 'INVALID_LOCATION',
    'sub-01/sub-01_channels.tsv': 'ALL_FILENAME_RULES_HAVE_ISSUES',
}


def build_dataset(root: Path) -> Path:
    """Create the example dataset under ``root``."""
    (root / 'dataset_description.json').write_text(
        json.dumps({'Name': 'filename example', 'BIDSVersion': '1.11.1'})
    )
    for relpath in (*VALID_FILES, *BROKEN_FILES):
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'')
    return root


def validate(root: Path) -> None:
    """Validate a dataset and print every filename finding."""
    tree = FileTree.read_from_filesystem(str(root))
    issues = collect_filename_issues(tree, load_schema())

    errors = issues.by_severity(Severity.ERROR)
    warnings = issues.by_severity(Severity.WARNING)

    print(f'dataset: {root}')
    print(f'{len(issues)} finding(s): {len(errors)} error(s), {len(warnings)} warning(s)\n')
    for issue in issues:
        print(f'[{issue.severity.value}] {issue.code}')
        print(f'    file   : {issue.location}')
        print(f'    detail : {issue.message}')
        if issue.rule:
            print(f'    rule   : {issue.rule}')
    print(f'\nvalid: {"no, errors found" if issues.has_errors else "yes"}')


def run_demo() -> None:
    """Build the generated example dataset and validate it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_dataset(Path(tmp))
        print('Generated example: one broken file per issue code.\n')
        for relpath, code in BROKEN_FILES.items():
            print(f'  {code:32} {relpath}')
        print()
        validate(root)


def main(argv: list[str]) -> int:
    """Run the demo, or validate the dataset given as the first argument."""
    if argv:
        validate(Path(argv[0]))
    else:
        run_demo()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
