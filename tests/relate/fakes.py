"""In-memory stand-in for `LinkLookupPort`."""

from __future__ import annotations

from ember.relate.rows import Link, NewItem


class FakeLinkLookup:
    def __init__(
        self,
        items: list[NewItem],
        links: list[Link] | None = None,
        latest: NewItem | None = None,
    ) -> None:
        self._items = list(items)
        self._links = list(links or [])
        self._latest = latest
        self._by_id = {item.id: item for item in self._items}

    def item_exists(self, item_id: int) -> bool:
        return item_id in self._by_id

    def item_type(self, item_id: int) -> str | None:
        item = self._by_id.get(item_id)
        return item.type if item is not None else None

    def item_statement(self, item_id: int) -> str | None:
        item = self._by_id.get(item_id)
        return item.statement if item is not None else None

    def item_created_at(self, item_id: int) -> str | None:
        item = self._by_id.get(item_id)
        return item.created_at if item is not None else None

    def find_existing(
        self, source_id: int, target_id: int, link_type: str
    ) -> Link | None:
        for link in self._links:
            triple = (link.source_item_id, link.target_item_id, link.link_type)
            if triple == (source_id, target_id, link_type):
                return link
        return None

    def existing_link_types(self, source_item_id: int) -> dict[int, set[str]]:
        existing: dict[int, set[str]] = {}
        for link in self._links:
            if link.source_item_id == source_item_id:
                existing.setdefault(link.target_item_id, set()).add(link.link_type)
        return existing

    def list_other_items(self, new_item_id: int) -> list[NewItem]:
        return [item for item in self._items if item.id != new_item_id]

    def find_latest_unlinked_active(self) -> NewItem | None:
        return self._latest

    def neighbors_of(self, item_id: int) -> list[int]:
        neighbors: set[int] = set()
        for link in self._links:
            if link.status != "Confirmed":
                continue
            if link.source_item_id == item_id:
                neighbors.add(link.target_item_id)
            elif link.target_item_id == item_id:
                neighbors.add(link.source_item_id)
        return sorted(neighbors)


class FakeEmbedder:
    """Canned embedder. Unknown text gets a fixed unit vector."""

    def __init__(
        self,
        vectors: dict[str, list[float]] | None = None,
        *,
        model_name: str = "fake-model",
        dim: int = 3,
        error: Exception | None = None,
    ) -> None:
        self._vectors = dict(vectors or {})
        self._model_name = model_name
        self._dim = dim
        self._error = error
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self._error is not None:
            raise self._error
        vectors: list[list[float]] = []
        for text in texts:
            vector = self._vectors.get(text)
            if vector is None:
                vector = [1.0] + [0.0] * (self._dim - 1)
            vectors.append(list(vector))
        return vectors

    def dim(self) -> int:
        return self._dim

    def model_name(self) -> str:
        return self._model_name


class FakeEmbeddingStore:
    """In-memory `item_embeddings` cache."""

    def __init__(
        self,
        rows: dict[int, list[float]] | None = None,
        *,
        model_name: str = "fake-model",
    ) -> None:
        self.rows = {item_id: list(vector) for item_id, vector in (rows or {}).items()}
        self.model_names = {item_id: model_name for item_id in self.rows}
        self.upserts: list[tuple[int, list[float], str]] = []
        self.wipes = 0

    def get(self, item_id: int) -> list[float] | None:
        return self.rows.get(item_id)

    def upsert(self, item_id: int, vector: list[float], model_name: str) -> None:
        self.upserts.append((item_id, list(vector), model_name))
        self.rows[item_id] = list(vector)
        self.model_names[item_id] = model_name

    def model_name_of(self, item_id: int) -> str | None:
        return self.model_names.get(item_id)

    def first_model_name(self) -> str | None:
        return next(iter(self.model_names.values()), None)

    def wipe(self) -> None:
        self.wipes += 1
        self.rows.clear()
        self.model_names.clear()
