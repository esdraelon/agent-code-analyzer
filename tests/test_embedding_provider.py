from __future__ import annotations

from agent_code_analyzer.embedding_provider import SentenceTransformerEmbeddingProvider


class FakeVector:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return list(self._values)


class FakeModel:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, texts, normalize_embeddings, convert_to_numpy, show_progress_bar):
        self.calls.append(list(texts))
        return [FakeVector([1.0, 2.0, 3.0])]


def test_sentence_transformer_provider_prefixes_documents_and_queries(monkeypatch) -> None:
    provider = SentenceTransformerEmbeddingProvider(model_name="demo-model")
    fake_model = FakeModel()
    monkeypatch.setattr(provider, "_load_model", lambda: fake_model)

    document_vector = provider.embed_document("alpha")
    query_vector = provider.embed_query("beta")

    assert document_vector == [1.0, 2.0, 3.0]
    assert query_vector == [1.0, 2.0, 3.0]
    assert fake_model.calls == [["passage: alpha"], ["query: beta"]]
    assert provider.vector_size == 3
