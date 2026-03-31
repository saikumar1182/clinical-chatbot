from pathlib import Path
import yaml

# This code is a small prompt registry loader.
# read prompts.yml
# keep the prompt definitions in memory
# return a selected prompt version
# list all available versions
# find the version with the highest evaluation score

# A module-level variable that acts as an in-memory cache. 
# The leading underscore _ signals it's private (internal use only).
_REGISTRY: dict | None = None

def _load_prompts():
    """Load prompts from YAML file into memory cache."""
    global _REGISTRY

    # Lazy loading: load only when first needed
    if _REGISTRY is None:
        path = Path(__file__).parent / "prompts.yml"
        with open(path) as f:
            _REGISTRY = yaml.safe_load(f)["versions"]
    return _REGISTRY

# get a specific prompt version
def get_prompt(version: str = "v4") -> tuple[str, str]:
    """Return a specific prompt version."""

    return _load_prompts()[version]["system"], _load_prompts()[version]["human"]


# list all available versions
def list_versions() -> list[dict]:
    """Return a list of available prompt versions."""
    return[
        {
            "version": k,
            "eval_score": v.get("eval_score"),
            "notes": v.get("notes"),
        }
        for k, v in _load_prompts().items()
    ]


def get_best_prompt() -> str:
    """Return the prompt version with the highest evaluation score."""
    return max(_load_prompts().items(), key=lambda x: x[1].get("eval_score", 0))[0]
    
