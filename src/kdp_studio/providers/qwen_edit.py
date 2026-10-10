"""Qwen Image Edit on a RunPod serverless endpoint: a picture repainted, not recomposed.

The endpoint takes the picture as `image_base64` with a prompt, a seed and a
size, and returns `{"image": <base64>}` (the wire format of Cine Toaster's
endpoint). Here it serves one need above all: taking the lettering out of a
picture a model drew with words in it, so the cover template can set them.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from . import ArtRequest, ArtResult, ProviderError, ProviderNotConfigured, setting
from .runpod import Transport, run_job, seconds

MODEL = "qwen-image-edit"
#: Cine Toaster's figures for this endpoint; `KDP_ART_HOURLY_USD` replaces the rate.
HOURLY_RATE_USD = 1.58
EXECUTION_SECONDS = 45.0
COLD_START_SECONDS = 90.0


class QwenEdit:
    id = "qwen-edit"
    model = MODEL
    mode = "edit"
    max_side = 1536

    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport

    def missing(self) -> list[str]:
        return [name for name in ("RUNPOD_API_KEY", "RUNPOD_QWEN_ENDPOINT_ID") if not setting(name)]

    def estimate_usd(self) -> float:
        rate = float(setting("KDP_ART_HOURLY_USD") or HOURLY_RATE_USD)
        return round((EXECUTION_SECONDS + COLD_START_SECONDS) * rate / 3600, 3)

    def run(self, request: ArtRequest, output: Path, state_file: Path) -> ArtResult:
        if self.missing():
            raise ProviderNotConfigured("Qwen Image Edit is not configured: " + ", ".join(self.missing()))
        if request.source is None:
            raise ProviderError("Qwen Image Edit repaints a picture: it needs one to start from")
        from PIL import Image

        with Image.open(request.source) as opened:
            picture = opened.convert("RGB").resize((request.width, request.height), Image.LANCZOS)
        buffer = io.BytesIO()
        picture.save(buffer, "PNG")
        endpoint = setting("RUNPOD_QWEN_ENDPOINT_ID")
        payload = {"prompt": request.prompt, "seed": request.seed, "width": request.width, "height": request.height,
                   "image_base64": base64.b64encode(buffer.getvalue()).decode()}
        result, state = run_job(endpoint, payload, state_file=state_file, label="qwen-edit", transport=self.transport)
        data = result.get("image")
        if not data:
            raise ProviderError("qwen-edit: the worker returned no image", endpoint=endpoint)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(base64.b64decode(str(data).split(",", 1)[-1]))
        rate = float(setting("KDP_ART_HOURLY_USD") or HOURLY_RATE_USD)
        return ArtResult(output, self.id, self.model, request.seed, seconds(state),
                         round(seconds(state) * rate / 3600, 4), {"endpoint": endpoint, "job": state.get("id")})
