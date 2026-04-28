from scripts.build_real_paper_eval_dataset import build_dataset


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def get(self, url, params):
        self.calls.append((url, params))
        return _FakeResponse(
            {
                "results": [
                    {
                        "document_id": "00000000-0000-4000-8000-000000000001",
                        "chunk_index": 7,
                    }
                ]
            }
        )


def test_build_dataset_creates_answerable_and_unanswerable_cases(monkeypatch):
    monkeypatch.setattr("scripts.build_real_paper_eval_dataset.httpx.Client", _FakeClient)

    dataset = build_dataset("http://testserver", method="bm25", top_k=3)

    assert dataset["method"] == "bm25"
    assert dataset["top_k"] == 3
    assert len(dataset["cases"]) == 20
    answerable = [case for case in dataset["cases"] if case["answerable"]]
    unanswerable = [case for case in dataset["cases"] if not case["answerable"]]
    assert len(answerable) == 12
    assert len(unanswerable) == 8
    assert answerable[0]["expected_chunk_index"] == 7
