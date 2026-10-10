"""RunPod serverless, data plane only: submit a job, wait, take the result.

The state file is the point. Generation is slow and paid for; a lost
connection must not send again work that is already queued. Before anything
is sent the request is recorded with a digest of itself, so a second run can
tell "the same request, still running" from "a different one", and refuses
the ambiguous case rather than spend money guessing. (Cine Toaster, runpod.py.)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from . import ProviderError, ProviderNotConfigured, setting

RUN_BASE = "https://api.runpod.ai/v2"
TERMINAL_FAILURES = ("FAILED", "CANCELLED", "TIMED_OUT")
RETRIABLE_STATUS = {429, 500, 502, 503, 504}
POLL_SECONDS = 5.0
REQUEST_TIMEOUT = 300
MAX_TRANSPORT_ATTEMPTS = 5

Transport = Callable[[str, dict[str, Any] | None], dict[str, Any]]


def request(path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """One call against the serverless API; POST when there is a body."""

    key = setting("RUNPOD_API_KEY")
    if not key:
        raise ProviderNotConfigured("RUNPOD_API_KEY is not set")
    payload = json.dumps(body).encode() if body is not None else None
    http = urllib.request.Request(f"{RUN_BASE}{path}", data=payload, method="POST" if payload else "GET")
    http.add_header("Authorization", f"Bearer {key}")
    http.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(http, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read())


def _write(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _poll(send: Transport, endpoint: str, job_id: str, state: dict[str, Any], state_file: Path) -> dict[str, Any]:
    for attempt in range(MAX_TRANSPORT_ATTEMPTS):
        try:
            return send(f"/{endpoint}/status/{job_id}", None)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                # The job left the queue: terminal, so the next attempt may send again.
                state["status"] = "FAILED"
                _write(state_file, state)
                raise ProviderError(f"Job {job_id} is no longer in the queue (404)", job_id=job_id) from error
            if error.code not in RETRIABLE_STATUS or attempt == MAX_TRANSPORT_ATTEMPTS - 1:
                raise ProviderError(f"Job {job_id}: HTTP {error.code}", job_id=job_id) from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == MAX_TRANSPORT_ATTEMPTS - 1:
                raise ProviderError(f"Job {job_id}: {error}", job_id=job_id) from error
        time.sleep(2 ** attempt)
    raise ProviderError(f"Job {job_id}: exhausted transport attempts", job_id=job_id)


def run_job(endpoint: str, payload: dict[str, Any], *, state_file: Path, label: str = "job",
            transport: Transport | None = None, poll_seconds: float = POLL_SECONDS) -> tuple[dict[str, Any], dict[str, Any]]:
    """Submit one job and wait. Returns its output and the state recorded for it."""

    if not endpoint:
        raise ProviderNotConfigured("No endpoint id was given for this provider")
    send = transport or request
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    state: dict[str, Any] = {}
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
    pending = bool(state) and state.get("status") not in (*TERMINAL_FAILURES, "COMPLETED")
    if pending:
        if state.get("sha256") != digest or state.get("endpoint") != endpoint:
            raise ProviderError(f"{state_file} records a different pending request. Check the provider's queue "
                                "before sending again, so paid work is not duplicated.", state_file=str(state_file))
        if not state.get("id"):
            raise ProviderError(f"{state_file} records a submission with no confirmed id. Check the provider's "
                                "queue before sending again.", state_file=str(state_file))
    else:
        state = {"endpoint": endpoint, "sha256": digest, "status": "SUBMITTING"}
        _write(state_file, state)
        response = send(f"/{endpoint}/run", {"input": payload})
        state.update(id=response["id"], status=response.get("status", "IN_QUEUE"))
        _write(state_file, state)
    while True:
        status = _poll(send, endpoint, state["id"], state, state_file)
        state.update({key: status[key] for key in ("status", "delayTime", "executionTime", "workerId")
                      if key in status})
        _write(state_file, state)
        if status.get("status") in ("COMPLETED", *TERMINAL_FAILURES):
            break
        time.sleep(poll_seconds)
    output = status.get("output")
    if status.get("status") != "COMPLETED" or (isinstance(output, dict) and output.get("error")):
        state["status"] = "FAILED"
        _write(state_file, state)
        detail = output.get("error") if isinstance(output, dict) else None
        raise ProviderError(f"{label}: {status.get('error') or detail or status.get('status')}",
                            job_id=state["id"], endpoint=endpoint)
    return (output if isinstance(output, dict) else {}), state


def seconds(state: dict[str, Any]) -> float:
    """Billable time of a recorded job: queue and cold start, then execution."""

    return (float(state.get("delayTime") or 0) + float(state.get("executionTime") or 0)) / 1000
