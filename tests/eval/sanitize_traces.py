import json
import re
import sys
from pathlib import Path

# Headers, env vars, and properties that must be stripped or masked
SENSITIVE_KEYS = {
    "authorization",
    "x-stagehand-admin-key",
    "grafana_service_account_token",
    "grafana_cloud_otlp_token",
    "google_api_key",
    "gemini_api_key",
    "stagehand_admin_token",
    "terraform",
    "tfstate",
}

# Regex to match potential secrets, tokens, and authorization values
SENSITIVE_PATTERNS = [
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]+"), "Bearer [MASKED]"),
    (re.compile(r"Basic\s+[a-zA-Z0-9_\-\.\+/=]+"), "Basic [MASKED]"),
    (re.compile(r"https?://[a-zA-Z0-9_\-\.\+]+:[^@/]+@"), "https://[MASKED_CREDENTIALS]@"),
    (re.compile(r"glpat-[a-zA-Z0-9_\-]{20,25}"), "glpat-[MASKED]"),
    # Grafana tokens use a distinctive prefix, but their payload may contain
    # URL-safe punctuation and test/staging credentials may be shorter.
    (re.compile(r"gl(sa|c)_[a-zA-Z0-9._-]+"), r"gl\1_[MASKED]"),
    (re.compile(r"AIzaSy[a-zA-Z0-9_\-]{33}"), "AIzaSy[MASKED]"),
    (
        re.compile(
            r"\b(stagehand_admin_token|grafana_service_account_token|grafana_cloud_otlp_token|google_api_key|gemini_api_key|x-stagehand-admin-key|authorization)\b\s*([=:])\s*['\"]?[a-zA-Z0-9_\-\.\+/=]+['\"]?",
            re.IGNORECASE,
        ),
        r"\1\2[MASKED]",
    ),
]


def sanitize_object(obj):
    """Recursively traverse and sanitize dicts/lists to remove secrets."""
    if isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            k_lower = k.lower()
            if any(sensitive in k_lower for sensitive in SENSITIVE_KEYS):
                new_obj[k] = "[MASKED_SECRET]"
            else:
                new_obj[k] = sanitize_object(v)
        return new_obj
    elif isinstance(obj, list):
        return [sanitize_object(item) for item in obj]
    elif isinstance(obj, str):
        val = obj
        for pattern, replacement in SENSITIVE_PATTERNS:
            val = pattern.sub(replacement, val)
        return val
    else:
        return obj


def _assert_no_secrets(obj) -> None:
    """Recursively verify that no sensitive keys contain raw secrets."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_lower = k.lower()
            if any(sensitive in k_lower for sensitive in SENSITIVE_KEYS):
                if v != "[MASKED_SECRET]" and v != "[MASKED]":
                    raise ValueError(f"Sensitive key '{k}' contains unmasked value: {v}")
            _assert_no_secrets(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_secrets(item)


def verify_sanitized(text: str) -> None:
    """Strictly assert that no sensitive data remains in the serialized output."""
    # 1. Regex check for raw patterns
    for pattern, _ in SENSITIVE_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"Sensitive pattern match found: {pattern.pattern}")

    # 2. Key-value check in JSON structure
    try:
        try:
            data = json.loads(text)
            _assert_no_secrets(data)
        except json.JSONDecodeError:
            for line in text.splitlines():
                if line.strip():
                    data = json.loads(line)
                    _assert_no_secrets(data)
    except Exception as e:
        raise ValueError(f"Verification failed to parse output JSON: {e}") from e


def sanitize_file(file_path: Path) -> None:
    """Read a JSON/JSONL trace file, sanitize all secrets, and write it back."""
    print(f"Sanitizing: {file_path}")
    try:
        content = file_path.read_text(encoding="utf-8")
        # Try as JSON first
        try:
            data = json.loads(content)
            sanitized_data = sanitize_object(data)
            output = json.dumps(sanitized_data, indent=2)
        except json.JSONDecodeError:
            # Fall back to JSONL
            lines = content.splitlines()
            sanitized_lines = []
            for line in lines:
                if not line.strip():
                    continue
                # JSONL lines must be valid JSON; fail if they are not
                line_data = json.loads(line)
                sanitized_line_data = sanitize_object(line_data)
                sanitized_lines.append(json.dumps(sanitized_line_data))
            output = "\n".join(sanitized_lines) + "\n"

        # Validate that the sanitization succeeded completely before writing
        verify_sanitized(output)
        file_path.write_text(output, encoding="utf-8")
    except Exception as e:
        print(f"CRITICAL: Failed to sanitize {file_path}. Failing closed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python sanitize_traces.py <file_or_directory_path>", file=sys.stderr)
        sys.exit(1)

    target_path = Path(sys.argv[1])
    if not target_path.exists():
        print(f"Error: Path {target_path} does not exist.", file=sys.stderr)
        sys.exit(1)

    if target_path.is_file():
        sanitize_file(target_path)
    else:
        # Directory - walk and sanitize all JSON/JSONL files
        for ext in ("*.json", "*.jsonl"):
            for p in target_path.rglob(ext):
                sanitize_file(p)
    print("Sanitization complete.")


if __name__ == "__main__":
    main()
