"""Small async fakes for application ports shared across feature tests."""

from __future__ import annotations


class FakeModel:
    def __init__(self, output=""):
        self.output = output
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.output


class FakeSearchPort:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    async def search(self, query, **options):
        self.calls.append({"query": query, "options": options})
        return list(self.results)


class FakeMakerStore:
    """Minimal tenant-scoped Maker Store contract; no unscoped access exists."""

    def __init__(self):
        self.values = {}
        self.calls = []

    async def get(self, tenant_id, key):
        self.calls.append(("get", tenant_id, key))
        return self.values.get((tenant_id, key))

    async def put(self, tenant_id, key, value):
        self.calls.append(("put", tenant_id, key, value))
        self.values[(tenant_id, key)] = value


class FakeComponentPublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, tenant_id, action, payload):
        record = {"tenant_id": tenant_id, "action": action, "payload": payload}
        self.calls.append(record)
        return record
