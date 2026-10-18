"""One entry point for affairs: federal from the local bulk table when loaded (D11), others from the API."""

from parltopics.config import Settings
from parltopics.sources.api import Affair, OPDClient
from parltopics.sources.bulk import BULK_BODY_KEY, BulkReader


class AffairSource:
    def __init__(self, settings: Settings):
        self.api = OPDClient(settings)
        self.bulk = (
            BulkReader(settings.bulk_db_path, self.api.get_body(BULK_BODY_KEY))
            if settings.bulk_db_path.exists() else None
        )

    def get_affair(self, affair_id: int, body_key: str | None = None) -> Affair:
        if self.bulk is not None and body_key == BULK_BODY_KEY:
            try:
                return self.bulk.get_affair(affair_id)
            except KeyError:
                pass
        return self.api.get_affair(affair_id)
