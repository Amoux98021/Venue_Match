from pathlib import Path

import pytest

from src.db.database import initialize_database
from src.utils.api_quota import (
    ProviderQuotaExceeded,
    get_provider_usage,
    reserve_provider_call,
)


def test_provider_quota_stops_before_overage(tmp_path: Path) -> None:
    database_path = tmp_path / "quota.db"
    initialize_database(database_path)

    assert reserve_provider_call("jambase", 3, database_path) == 1
    assert reserve_provider_call("jambase", 3, database_path) == 2
    assert reserve_provider_call("jambase", 3, database_path) == 3
    with pytest.raises(ProviderQuotaExceeded):
        reserve_provider_call("jambase", 3, database_path)

    usage = get_provider_usage(database_path)[0]
    assert usage["calls_used"] == 3
    assert usage["remaining"] == 0
