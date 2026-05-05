from __future__ import annotations

from orderflow_api.core.hash_utils import calculate_page_content_hash


def test_calculate_page_content_hash_deterministic() -> None:
    text1 = "This is\n a   test\tpage."
    text2 = "This is a test page."
    text3 = "  This is a test page.  \n"

    hash1 = calculate_page_content_hash(text1)
    hash2 = calculate_page_content_hash(text2)
    hash3 = calculate_page_content_hash(text3)

    assert hash1 == hash2 == hash3
    assert len(hash1) == 64


def test_calculate_page_content_hash_empty() -> None:
    empty_hash = calculate_page_content_hash("")
    none_hash = calculate_page_content_hash(None)
    whitespace_hash = calculate_page_content_hash("   \n\t  ")

    assert empty_hash == none_hash == whitespace_hash
    assert len(empty_hash) == 64
