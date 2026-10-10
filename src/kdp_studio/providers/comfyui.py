"""ComfyUI on a RunPod serverless endpoint: a picture from words.

The graph is the author's: a workflow exported from ComfyUI in API format,
for the models their endpoint holds (`KDP_COMFYUI_WORKFLOW`). KDP Studio only
sets the prompt, the negative prompt, the seed and the size -- by node *type*,
because node numbers change every time a workflow is exported again.
"""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from typing import Any

from . import ArtRequest, ArtResult, ProviderError, ProviderNotConfigured, setting
from .runpod import Transport, run_job, seconds

#: Cine Toaster's figures for its ComfyUI endpoint; `KDP_ART_HOURLY_USD` replaces the rate.
HOURLY_RATE_USD = 1.22
EXECUTION_SECONDS = 40.0
COLD_START_SECONDS = 120.0


def patch_workflow(workflow: dict[str, Any], *, prompt: str, negative: str, seed: int, width: int,
                   height: int) -> dict[str, Any]:
    patched = copy.deepcopy(workflow)
    positive_done = False
    for node in patched.values():
        if not isinstance(node, dict):
            continue
        kind = str(node.get("class_type", ""))
        inputs = node.setdefault("inputs", {})
        if kind == "CLIPTextEncode":
            # Convention: a node titled "neg…" is the negative prompt; the first other one is the prompt.
            if str(node.get("_meta", {}).get("title", "")).lower().startswith("neg"):
                inputs["text"] = negative
            elif not positive_done:
                inputs["text"] = prompt
                positive_done = True
        elif kind == "KSampler":
            inputs["seed"] = seed
        elif kind == "RandomNoise":
            inputs["noise_seed"] = seed
        elif "LatentImage" in kind and "width" in inputs and "height" in inputs:
            inputs["width"], inputs["height"] = width, height
    if not positive_done:
        raise ProviderError("The ComfyUI workflow has no CLIPTextEncode node to carry the prompt")
    return patched


class ComfyUi:
    id = "comfyui"
    mode = "generate"
    max_side = 1536

    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport

    @property
    def model(self) -> str:
        return setting("KDP_COMFYUI_MODEL") or "comfyui-workflow"

    def missing(self) -> list[str]:
        needed = ["RUNPOD_API_KEY", "KDP_COMFYUI_ENDPOINT_ID", "KDP_COMFYUI_WORKFLOW"]
        missing = [name for name in needed if not setting(name)]
        workflow = setting("KDP_COMFYUI_WORKFLOW")
        if workflow and not Path(workflow).expanduser().is_file():
            missing.append(f"KDP_COMFYUI_WORKFLOW (no file at {workflow})")
        return missing

    def estimate_usd(self) -> float:
        rate = float(setting("KDP_ART_HOURLY_USD") or HOURLY_RATE_USD)
        return round((EXECUTION_SECONDS + COLD_START_SECONDS) * rate / 3600, 3)

    def run(self, request: ArtRequest, output: Path, state_file: Path) -> ArtResult:
        if self.missing():
            raise ProviderNotConfigured("ComfyUI is not configured: " + ", ".join(self.missing()))
        path = Path(setting("KDP_COMFYUI_WORKFLOW")).expanduser()
        try:
            workflow = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ProviderError(f"Unreadable ComfyUI workflow {path}: {error}") from error
        patched = patch_workflow(workflow, prompt=request.prompt, negative=request.negative, seed=request.seed,
                                 width=request.width, height=request.height)
        endpoint = setting("KDP_COMFYUI_ENDPOINT_ID")
        result, state = run_job(endpoint, {"workflow": patched}, state_file=state_file, label="comfyui",
                                transport=self.transport)
        images = [image for image in result.get("images") or []
                  if not (isinstance(image, dict) and image.get("type") == "s3_url")]
        if not images:
            raise ProviderError("comfyui: the worker returned no image", endpoint=endpoint)
        blob = images[0].get("data") if isinstance(images[0], dict) else images[0]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(base64.b64decode(str(blob).split(",", 1)[-1]))
        rate = float(setting("KDP_ART_HOURLY_USD") or HOURLY_RATE_USD)
        return ArtResult(output, self.id, self.model, request.seed, seconds(state),
                         round(seconds(state) * rate / 3600, 4),
                         {"endpoint": endpoint, "job": state.get("id"), "workflow": path.name})
