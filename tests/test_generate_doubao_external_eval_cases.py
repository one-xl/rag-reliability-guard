"""Offline tests for live Doubao external-eval dataset generation script."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.config import DoubaoSettings
from scripts.generate_doubao_external_eval_cases import (
    build_live_dataset_payload,
    evidence_to_doubao_citations,
    load_source,
    main as script_main,
)


_SAMPLE_SOURCE = {
    "min_support_rate": 0.5,
    "cases": [
        {
            "case_id": "c-supported",
            "question": " What is RAG? ",
            "answerable": True,
            "evidence": [
                {
                    "evidence_id": "kb#1",
                    "source": "notes.md",
                    "text": "RAG retrieves then generates.",
                }
            ],
        },
        {
            "case_id": "c-empty",
            "question": "Secret password?",
            "answerable": False,
            "evidence": [],
        },
    ],
}


def test_evidence_to_doubao_citations_empty():
    assert evidence_to_doubao_citations([]) == []
    assert evidence_to_doubao_citations(None) == []


def test_evidence_to_doubao_citations_maps_fields():
    cits = evidence_to_doubao_citations(
        [{"evidence_id": "a", "source": "f.txt", "text": "hello"}]
    )
    assert len(cits) == 1
    assert cits[0]["index"] == 1
    assert cits[0]["original_filename"] == "f.txt"
    assert cits[0]["chunk_index"] == 0
    assert cits[0]["text_preview"] == "hello"


def test_build_live_dataset_payload_monkeypatched(tmp_path):
    calls: list[tuple[str, int]] = []

    def fake_gen(question: str, citations: list) -> str:
        calls.append((question, len(citations)))
        return f"a-for-{question[:8]}-{len(citations)}"

    dataset = Path(tmp_path / "src.json")
    dataset.write_text(json.dumps(_SAMPLE_SOURCE, ensure_ascii=False), encoding="utf-8")
    loaded = load_source(dataset)

    out = build_live_dataset_payload(
        loaded,
        run_id="run-test-1",
        model="doubao-unit",
        provider="volcengine",
        answer_generator=fake_gen,
    )

    assert out["min_support_rate"] == 0.5
    assert "_comment" in out
    assert len(out["cases"]) == 2
    c0 = out["cases"][0]
    assert c0["provider"] == "volcengine"
    assert c0["model"] == "doubao-unit"
    assert c0["run_id"] == "run-test-1"
    assert c0["case_id"] == "c-supported"
    assert c0["question"] == "What is RAG?"
    assert c0["answerable"] is True
    assert len(c0["evidence"]) == 1
    assert c0["evidence"][0]["text"] == "RAG retrieves then generates."
    assert c0["answer"].startswith("a-for-What")

    c1 = out["cases"][1]
    assert c1["answerable"] is False
    assert c1["evidence"] == []
    assert c1["answer"].endswith("-0")

    assert calls == [
        ("What is RAG?", 1),
        ("Secret password?", 0),
    ]


def test_main_writes_default_or_explicit_output(monkeypatch, tmp_path):
    fixed_ts = "20260429_120000"

    def fake_generate(q: str, citations: list) -> str:
        return "mock"

    fake_settings = DoubaoSettings(
        api_key="k",
        base_url="https://example/api/v3",
        model="doubao-from-env",
        timeout_seconds=1.0,
    )

    class _FixedNow:
        def strftime(self, fmt: str) -> str:
            return fixed_ts

    class _FixedDateTime:
        @staticmethod
        def now():
            return _FixedNow()

    monkeypatch.setattr(
        "scripts.generate_doubao_external_eval_cases.datetime",
        _FixedDateTime,
    )

    monkeypatch.setattr(
        "scripts.generate_doubao_external_eval_cases.generate_doubao_answer",
        fake_generate,
    )
    monkeypatch.setattr(
        "scripts.generate_doubao_external_eval_cases.get_doubao_settings",
        lambda: fake_settings,
    )

    tiny = {"min_support_rate": 0.5, "cases": [{"case_id": "x", "question": "Hi?", "answerable": True, "evidence": []}]}
    src = tmp_path / "source.json"
    src.write_text(json.dumps(tiny, ensure_ascii=False), encoding="utf-8")

    expected_default = tmp_path / "data" / "experiments" / f"doubao_external_eval_cases_{fixed_ts}.json"

    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(sys, "argv", ["generate_doubao_external_eval_cases.py", "--source", str(src)])

    rc = script_main()
    assert rc == 0
    assert expected_default.is_file()
    payload = json.loads(expected_default.read_text(encoding="utf-8"))
    assert payload["cases"][0]["model"] == "doubao-from-env"
    assert payload["cases"][0]["provider"] == "volcengine"
    assert payload["cases"][0]["run_id"] == f"doubao-live-{fixed_ts}"

    explicit = tmp_path / "explicit_out.json"

    monkeypatch.setattr(sys, "argv", [
        "_",
        "--source",
        str(src),
        "--output",
        str(explicit),
        "--run-id",
        "custom-run",
    ])
    rc2 = script_main()
    assert rc2 == 0
    assert explicit.is_file()
    pl2 = json.loads(explicit.read_text(encoding="utf-8"))
    assert pl2["cases"][0]["run_id"] == "custom-run"
