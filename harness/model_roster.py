from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    thesis_model: str
    adversary_model: str
    default_reviewer_model: str
    reviewer_models: dict[str, str]
    translator_model: str | None = None
    post_audit_model: str | None = None


CONFIRMED_LOCAL_PROFILE = ModelProfile(
    profile_id="confirmed-local",
    thesis_model="qwen3.5:9b",
    adversary_model="qwen2.5-coder:14b",
    default_reviewer_model="qwen3.5:9b",
    reviewer_models={
        "code_reviewer": "gemma4:12b",
        "logic_reviewer": "phi4-reasoning:14b",
        "math_reviewer": "gpt-oss:20b",
        "physics_reviewer": "llama3.1:8b",
        "scope_reviewer": "ministral-3:14b",
        "blindspot_reviewer": "qwen3.5:9b",
    },
    translator_model="qwen3.5:9b",
    post_audit_model="olmo2:13b",
)


MODEL_PROFILES = {
    CONFIRMED_LOCAL_PROFILE.profile_id: CONFIRMED_LOCAL_PROFILE,
}
