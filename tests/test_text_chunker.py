"""text_chunker 行为与参数校验。"""

import pytest

from app.text_chunker import chunk_text


def test_chunking_no_overlap():
    assert chunk_text("abcdefgh", chunk_size=3, overlap=0) == ["abc", "def", "gh"]


def test_overlap_advances_by_chunk_minus_overlap():
    # chunk_size=4, overlap=1 -> step 3: [0:4], [3:7], [6:10]
    assert chunk_text("abcdefghij", chunk_size=4, overlap=1) == [
        "abcd",
        "defg",
        "ghij",
    ]


def test_empty_text_returns_empty_list():
    assert chunk_text("", chunk_size=10, overlap=0) == []


def test_rejects_non_positive_chunk_size():
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("abc", chunk_size=0, overlap=0)
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("abc", chunk_size=-1, overlap=0)


def test_rejects_negative_overlap():
    with pytest.raises(ValueError, match="overlap must be non-negative"):
        chunk_text("abc", chunk_size=3, overlap=-1)


def test_rejects_overlap_not_smaller_than_chunk_size():
    with pytest.raises(ValueError, match="smaller than chunk_size"):
        chunk_text("abc", chunk_size=3, overlap=3)
    with pytest.raises(ValueError, match="smaller than chunk_size"):
        chunk_text("abc", chunk_size=2, overlap=2)
