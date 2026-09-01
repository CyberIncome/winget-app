"""Robust decoding for WinGet/QProcess byte streams."""

from __future__ import annotations

import codecs
import locale


def _looks_utf16(data: bytes) -> str | None:
    """Return a likely UTF-16 endianness for BOM-less console output."""
    if len(data) < 4:
        return None
    sample = data[: min(len(data), 4096)]
    pairs = len(sample) // 2
    if not pairs:
        return None
    even_nuls = sample[0::2].count(0) / pairs
    odd_nuls = sample[1::2].count(0) / pairs
    if odd_nuls >= 0.25 and even_nuls < 0.10:
        return "utf-16-le"
    if even_nuls >= 0.25 and odd_nuls < 0.10:
        return "utf-16-be"
    return None


def _locale_encodings() -> list[str]:
    candidates = []
    for getter_name in ("getencoding", "getpreferredencoding"):
        getter = getattr(locale, getter_name, None)
        if getter is None:
            continue
        try:
            value = getter() if getter_name == "getencoding" else getter(False)
        except (TypeError, ValueError):
            continue
        if value:
            candidates.append(str(value))
    # ``mbcs`` resolves to the active Windows ANSI code page and is absent on
    # non-Windows hosts. Keeping it as a final strict candidate is harmless.
    candidates.append("mbcs")
    return candidates


def decode_process_bytes(data: bytes | bytearray | memoryview) -> str:
    """Decode process bytes without assuming every Winget build emits UTF-8."""
    raw = bytes(data or b"")
    if not raw:
        return ""

    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig", errors="replace")
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return raw.decode("utf-16", errors="replace")

    utf16 = _looks_utf16(raw)
    if utf16:
        try:
            return raw.decode(utf16, errors="strict")
        except UnicodeDecodeError:
            pass

    encodings = ["utf-8", *_locale_encodings()]
    seen = set()
    for encoding in encodings:
        normalized = encoding.lower().replace("_", "-")
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return raw.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue

    return raw.decode("utf-8", errors="replace")
