# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Fixed-SHA Native OCR subprocess adapter. Never execute reviewed project code."""

import ipaddress
import base64
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from .code_review_provider import provider_for
from .repository_transport import validate_instance
from .review_report import code_report_details

ALLOWED_EXCLUSIONS = {"binary", "deleted", "default_path", "provider_directory", "secret_exclude"}


class ExecutionFailure(Exception):
    def __init__(self, code, transient=False):
        self.code, self.transient = code, transient
        super().__init__(code)


def normalize_report(raw, diff_files, base, head, exit_code):
    """Unknown contracts or inconsistent coverage fail closed, even at exit zero."""
    coverage = {"diff_files": diff_files, "completed": [], "excluded": [], "missing": diff_files}
    report = {"summary": "无法确认审查完整性", "findings": [], "coverage": coverage}
    if not isinstance(raw, dict) or not isinstance(raw.get("comments"), list):
        return "failed", report
    if not diff_files and exit_code == 0 and not raw["comments"]:
        report.update(summary="无代码差异，等待人工确认", no_diff=True)
        coverage["missing"] = []
        code_report_details("completed", report, raw)
        return "completed", report
    manifest = raw.get("manifest") or {}
    inputs = manifest.get("input") or {}
    if (
        manifest.get("schema_version") != "ocr.run-manifest/v1"
        or manifest.get("operation") != "review"
        or inputs.get("resolved_base") != base
        or inputs.get("resolved_head") != head
    ):
        return "failed", report
    sets = manifest.get("coverage") or {}
    try:
        completed = sets.get("completed") or []
        reused = sets.get("reused") or []
        excluded = sets.get("excluded") or []
        failed = sets.get("failed") or []
        waived = sets.get("waived") or []
        selected = sets.get("selected") or []
        done = {x["path"] for x in completed + reused}
        allowed = {
            x["path"]
            for x in excluded
            if x.get("exclude_reason") in ALLOWED_EXCLUSIONS
            or (x.get("exclude_reason") == "user_exclude" and x["path"].startswith(".opencodereview/"))
        }
        all_paths = {x["path"] for x in selected + excluded}
        coverage.update(
            completed=sorted(done), excluded=excluded, failed=failed, missing=sorted(set(diff_files) - done - allowed)
        )
        findings = []
        for item in raw["comments"]:
            path = item.get("path")
            start = item.get("start_line", 0)
            end = item.get("end_line", start)
            if (
                path not in set(diff_files)
                or type(start) is not int
                or start < 0
                or type(end) is not int
                or end < start
                or not isinstance(item.get("content"), str)
            ):
                raise ValueError()
            findings.append(
                {
                    "path": path,
                    "line": start,
                    "end_line": end,
                    "severity": item.get("severity") or "unknown",
                    "message": item["content"],
                }
            )
        report["findings"] = findings
        incomplete = (
            bool(coverage["missing"] or failed or waived)
            or all_paths != set(diff_files)
            or {x["path"] for x in selected} != done
            or manifest.get("terminal_state") not in ("complete", "skipped")
            or manifest.get("run_failure")
            or (isinstance(raw.get("summary"), dict) and raw["summary"].get("budget_exceeded"))
            or any(w.get("type") in ("review_limit_reached", "subtask_error") for w in raw.get("warnings", []))
        )
    except (TypeError, KeyError, ValueError):
        return "failed", report
    status = "failed" if exit_code else "partial" if incomplete else "completed"
    report["summary"] = "审查完整，等待人工确认" if status == "completed" else "审查覆盖不完整，不能确认放行"
    code_report_details(status, report, raw)
    return status, report


def process(args, cwd, env, deadline, allow_failure=False):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ExecutionFailure("execution_timeout", True)
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as diagnostics:
        child = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=diagnostics,
            start_new_session=True,
        )
        try:
            child.wait(timeout=remaining)
        except BaseException:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise ExecutionFailure("execution_timeout", True) from None
        output.seek(0)
        data = output.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise ExecutionFailure("execution_output_too_large")
        if child.returncode and not allow_failure:
            diagnostics.seek(0)
            message = diagnostics.read(65536).lower()
            transient = any(
                value in message
                for value in (
                    b"timed out",
                    b"could not resolve host",
                    b"connection reset",
                    b"connection refused",
                    b"error: 429",
                    b"error: 502",
                    b"error: 503",
                    b"error: 504",
                )
            )
            raise ExecutionFailure("repository_prepare_failed", transient)
        return child.returncode, data


def changed_paths(checkout, env, deadline, base, head):
    """Inventory paths with the same rename semantics as Native OCR."""
    _, paths = process(["git", "diff", "--name-only", "--find-renames", "-z", base, head], checkout, env, deadline)
    return paths.decode("utf-8").rstrip("\0").split("\0") if paths else []


def run_ocr(run):
    deadline = time.monotonic() + 1800
    repo = run.link.repository
    provider = provider_for(repo)
    expected = run.snapshot["settings"]
    binary = os.environ.get("CODE_REVIEW_OCR_BINARY", "/usr/local/bin/ocr")
    key_file = os.environ.get("CODE_REVIEW_MODEL_KEY_FILE") or os.environ.get("DOCUMENT_REVIEW_MODEL_KEY_FILE")
    try:
        model_key = Path(key_file).read_text(encoding="utf-8-sig").strip()
        if not model_key:
            raise ValueError()
    except (TypeError, ValueError, OSError):
        raise ExecutionFailure("model_configuration_unavailable") from None
    with tempfile.TemporaryDirectory(prefix="plane-ocr-", dir=os.environ.get("CODE_REVIEW_WORK_ROOT")) as directory:
        work = Path(directory)
        checkout = work / "repo"
        checkout.mkdir()
        home = work / "home"
        home.mkdir()
        # Allowlist process environment: DB, Hatchet and repository credentials
        # cannot leak into OCR's tools or generated report.
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
        _, version = process([binary, "version"], work, env, deadline)
        if expected["tool_version"] not in version.decode("utf-8", errors="replace").split():
            # Versions may be prefixed with v by upstream releases.
            if ("v" + expected["tool_version"]) not in version.decode("utf-8", errors="replace").split():
                raise ExecutionFailure("ocr_version_mismatch")
        git_env = dict(env)
        url, networks = validate_instance(repo.instance)
        host = url.hostname
        port = url.port or (443 if url.scheme == "https" else 80)
        addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
        if not addresses or any(
            not ipaddress.ip_address(x).is_global and not any(ipaddress.ip_address(x) in n for n in networks)
            for x in addresses
        ):
            raise ExecutionFailure("repository_address_not_allowed")
        origin = (
            f"{url.scheme}://{url.netloc}" + url.path.removesuffix("/api/v4").rstrip("/") + "/" + repo.path + ".git"
        )
        # Token travels only in the Git child's environment; never argv or remote config.
        config = {
            "http.extraHeader": "Authorization: Basic "
            + base64.b64encode(("oauth2:" + provider.http.token).encode()).decode(),
            "http.followRedirects": "false",
            "http.curloptResolve": f"{host}:{port}:{addresses[0]}",
            "core.hooksPath": "/dev/null",
            "protocol.file.allow": "never",
            "submodule.recurse": "false",
        }
        if repo.instance.ca_file:
            config["http.sslCAInfo"] = repo.instance.ca_file
        git_env["GIT_CONFIG_COUNT"] = str(len(config))
        for index, (key, value) in enumerate(config.items()):
            git_env[f"GIT_CONFIG_KEY_{index}"] = key
            git_env[f"GIT_CONFIG_VALUE_{index}"] = value
        process(["git", "init", "--quiet"], checkout, git_env, deadline)
        process(
            [
                "git",
                "fetch",
                "--no-tags",
                "--no-recurse-submodules",
                origin,
                run.source_sha,
                run.target_sha,
                run.merge_base,
            ],
            checkout,
            git_env,
            deadline,
        )
        process(
            ["git", "-c", "core.hooksPath=/dev/null", "checkout", "--detach", "--force", run.source_sha],
            checkout,
            env,
            deadline,
        )
        _, computed = process(["git", "merge-base", run.merge_base, run.source_sha], checkout, env, deadline)
        if computed.decode().strip() != run.merge_base:
            raise ExecutionFailure("merge_base_mismatch")
        diff_files = changed_paths(checkout, env, deadline, run.merge_base, run.source_sha)
        # Never load repository-provided OCR/MCP configuration, hooks or symlinks.
        for path in checkout.rglob("*"):
            if path.is_symlink():
                path.unlink()
        project_config = checkout / ".opencodereview"
        if project_config.exists():
            import shutil

            if project_config.is_dir():
                shutil.rmtree(project_config)
            else:
                project_config.unlink()
        config_dir = home / ".opencodereview"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "provider": "openai-responses",
                    "model": expected["model"],
                    "language": "Simplified Chinese",
                    "providers": {
                        "openai-responses": {
                            "model": expected["model"],
                            "url": expected["model_url"],
                        }
                    },
                    "mcp_servers": {},
                }
            ),
            encoding="utf-8",
        )
        env["OPENAI_RESPONSES_API_KEY"] = model_key
        rule = work / "rule.json"
        rule.write_text(
            json.dumps(
                {
                    "exclude": [".opencodereview/**"],
                    "rules": [
                        {
                            "path": "**/*",
                            "rule": "所有代码审查问题的 content 必须使用简体中文。保留代码标识符原文。",
                            "merge_system_rule": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        output = work / "report.json"
        code, _ = process(
            [
                binary,
                "review",
                "--repo",
                str(checkout),
                "--from",
                run.merge_base,
                "--to",
                run.source_sha,
                "--format",
                "json",
                "--output",
                str(output),
                "--audience",
                "agent",
                "--rule",
                str(rule),
                "--concurrency",
                "2",
                "--effort",
                expected["effort"],
                "--background",
                "请使用中文报告代码缺陷。只审查代码，不执行项目脚本，不做需求符合性验收。",
            ],
            checkout,
            env,
            deadline,
            allow_failure=True,
        )
        try:
            if output.stat().st_size > 10 * 1024 * 1024:
                raise ValueError()
            content = output.read_text(encoding="utf-8")
            # Preserve original JSON unless a credential was echoed: fail without retaining it.
            if model_key in content or provider.http.token in content:
                raise ExecutionFailure("credential_in_report")
            raw = json.loads(content)
        except (OSError, ValueError):
            raise ExecutionFailure("invalid_ocr_json") from None
        status, report = normalize_report(raw, diff_files, run.merge_base, run.source_sha, code)
        return status, raw, report
