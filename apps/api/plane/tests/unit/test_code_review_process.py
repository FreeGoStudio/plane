# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
import os
import sys
import subprocess
import time
import pytest
from plane.singularity.code_review_runner import process, changed_paths, ExecutionFailure


def test_renames_use_ocr_destination_path(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, stderr=subprocess.DEVNULL).decode().strip()

    git("init")
    git("config", "user.email", "ocr-test@example.invalid")
    git("config", "user.name", "OCR test")
    (tmp_path / "before.py").write_text("def value():\n    return 42\n")
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    git("mv", "before.py", "after.py")
    git("commit", "-m", "rename")
    assert changed_paths(tmp_path, dict(os.environ), time.monotonic() + 5, base, "HEAD") == ["after.py"]


def test_authentication_failure_is_not_retried(tmp_path):
    with pytest.raises(ExecutionFailure) as failure:
        process(
            [sys.executable, "-c", "import sys;sys.stderr.write('Authentication failed');sys.exit(1)"],
            tmp_path,
            dict(os.environ),
            time.monotonic() + 5,
        )
    assert not failure.value.transient


def test_timeout_terminates_process(tmp_path):
    started = time.monotonic()
    with pytest.raises(ExecutionFailure) as failure:
        process([sys.executable, "-c", "import time;time.sleep(30)"], tmp_path, dict(os.environ), started + 0.2)
    assert failure.value.code == "execution_timeout"
    assert time.monotonic() - started < 3
