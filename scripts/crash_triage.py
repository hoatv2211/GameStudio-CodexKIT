from __future__ import annotations

import hashlib
import re
from typing import Any


ADDRESS_PREFIX = re.compile(r"^\s*0x[0-9a-fA-F]+\s+")


def triage_crash(payload: dict[str, Any]) -> dict[str, Any]:
    frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []
    normalized_frames = [ADDRESS_PREFIX.sub("", str(frame)).strip() for frame in frames]
    signature_source = "\n".join(
        [str(payload.get("build_id", "")), str(payload.get("exception", "")), *normalized_frames]
    )
    signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()
    hypotheses: list[str] = []
    exception = str(payload.get("exception", "")).casefold()
    if "access_violation" in exception or "segmentation" in exception:
        hypotheses.append("invalid memory access near the first application frame")
    if not payload.get("symbols_loaded", False):
        hypotheses.append("load matching symbols before assigning source-line blame")
    if not hypotheses:
        hypotheses.append("inspect the first application-owned frame and preceding state")
    return {
        "status": "PASS" if normalized_frames else "BLOCKED",
        "signature": signature,
        "build_id": payload.get("build_id"),
        "exception": payload.get("exception"),
        "normalized_frames": normalized_frames,
        "symbols_loaded": bool(payload.get("symbols_loaded", False)),
        "ranked_hypotheses": hypotheses,
    }
