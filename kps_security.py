import os
from typing import Iterable, List, Mapping, Any


def normalize_session_roots(roots: Iterable[str]) -> List[str]:
    """Return normalized absolute roots, preserving order and de-duplicating."""
    normalized: List[str] = []
    seen = set()
    for root in roots:
        if not isinstance(root, str) or not root.strip():
            continue
        abs_root = os.path.abspath(root)
        key = os.path.normcase(abs_root)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(abs_root)
    return normalized


def is_path_within_roots(path: str, roots: Iterable[str]) -> bool:
    """True if path is inside one of allowed roots (case-insensitive on Windows)."""
    if not isinstance(path, str) or not path.strip():
        return False
    abs_path = os.path.abspath(path)
    path_key = os.path.normcase(abs_path)
    for root in roots:
        abs_root = os.path.abspath(root)
        root_key = os.path.normcase(abs_root)
        if path_key == root_key or path_key.startswith(root_key + os.sep):
            return True
    return False


def sanitize_loaded_images(images_data: Iterable[Mapping[str, Any]], allowed_roots: Iterable[str]) -> List[dict]:
    """Filter malformed/untrusted session image records to allowed local roots only."""
    roots = normalize_session_roots(allowed_roots)
    sanitized: List[dict] = []
    for item in images_data:
        if not isinstance(item, Mapping):
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        if not os.path.isabs(path):
            continue
        if not is_path_within_roots(path, roots):
            continue
        if not os.path.exists(path):
            continue
        sanitized.append(dict(item))
    return sanitized


def resolve_non_conflicting_path(dst_path: str) -> str:
    """Return dst_path or suffixed variant if file already exists."""
    base, ext = os.path.splitext(dst_path)
    candidate = dst_path
    i = 1
    while os.path.exists(candidate):
        candidate = f"{base} ({i}){ext}"
        i += 1
    return candidate
