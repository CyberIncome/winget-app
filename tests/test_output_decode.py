"""Pure-Python tests for WinGet process-output decoding."""

from __future__ import annotations

import codecs

import src.logic.output_decode as output_decode


def test_utf8_output_decodes_normally():
    text = "Name Id Version Available Source\nCafé App Example.App 1.0 1.1 winget"
    assert output_decode.decode_process_bytes(text.encode("utf-8")) == text


def test_utf16_bom_is_detected():
    text = "Name Id Version Available Source\n日本語 App"
    encoded = codecs.BOM_UTF16_LE + text.encode("utf-16-le")
    assert output_decode.decode_process_bytes(encoded) == text


def test_bomless_utf16_le_ascii_table_is_detected():
    text = "Name   Id   Version   Available   Source\nExample App"
    assert output_decode.decode_process_bytes(text.encode("utf-16-le")) == text


def test_windows_locale_fallback_handles_shift_jis(monkeypatch):
    text = "名前 ID バージョン 一致 ソース"
    encoded = text.encode("cp932")
    monkeypatch.setattr(output_decode.locale, "getencoding", lambda: "cp932")
    monkeypatch.setattr(
        output_decode.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp932",
    )

    assert output_decode.decode_process_bytes(encoded) == text


def test_split_utf8_chunks_are_correct_when_reassembled_before_decode():
    text = "Café 日本語"
    encoded = text.encode("utf-8")
    split = encoded.index("é".encode("utf-8")) + 1
    first = encoded[:split]
    second = encoded[split:]

    # A live-console chunk may need replacement when it ends mid-codepoint,
    # but the protocol parser receives the reassembled raw byte stream.
    assert output_decode.decode_process_bytes(first + second) == text
