"""Fetch factual OpenRouter catalog data for tracked model vendors."""

import argparse
import json
import urllib.error
import urllib.request


MODELS_URL = "https://openrouter.ai/api/v1/models"
TRACKED_PREFIXES = ("openai/", "anthropic/")


def unavailable(reason):
    """Return the non-fatal signal used when the public catalog is unavailable."""
    return {"available": False, "reason": reason}


def fetch_facts(timeout=10):
    """Return a proposed factual reconcile from OpenRouter; never write files."""
    try:
        with urllib.request.urlopen(MODELS_URL, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status != 200:
                return unavailable("OpenRouter returned HTTP {}".format(status))
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError):
        return unavailable("OpenRouter catalog unavailable")
    except (json.JSONDecodeError, UnicodeError, ValueError, TypeError, KeyError):
        return unavailable("OpenRouter returned an invalid catalog")

    reconcile = []
    for model in payload.get("data", []):
        model_id = model.get("id", "")
        if not model_id.startswith(TRACKED_PREFIXES):
            continue
        pricing = model.get("pricing") or {}
        reconcile.append(
            {
                "id": model_id,
                "context_length": model.get("context_length"),
                "pricing_prompt": pricing.get("prompt"),
                "pricing_completion": pricing.get("completion"),
            }
        )
    return reconcile


def print_table(reconcile):
    """Print a compact human-readable view of the proposed reconcile."""
    if isinstance(reconcile, dict):
        print(json.dumps(reconcile))
        return

    print("id\tcontext_length\tpricing_prompt\tpricing_completion")
    for model in reconcile:
        print(
            "{id}\t{context_length}\t{pricing_prompt}\t{pricing_completion}".format(
                **model
            )
        )


def main(argv=None):
    """Run the read-only OpenRouter factual catalog command-line interface."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="as_json")
    arguments = parser.parse_args(argv)

    reconcile = fetch_facts()
    if arguments.as_json:
        print(json.dumps(reconcile))
    else:
        print_table(reconcile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
