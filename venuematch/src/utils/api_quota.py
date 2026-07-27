from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.db.database import DatabaseTarget, get_connection
from src.db.schema import provider_api_usage
from src.utils.config import get_env


JAMBASE_PROVIDER_LIMIT = 1_000
JAMBASE_SAFETY_RESERVE = 50
DEFAULT_JAMBASE_APP_LIMIT = JAMBASE_PROVIDER_LIMIT - JAMBASE_SAFETY_RESERVE


class ProviderQuotaExceeded(RuntimeError):
    """Raised before an API request that would exceed the local monthly budget."""


def jambase_monthly_limit() -> int:
    configured = get_env("JAMBASE_MONTHLY_CALL_LIMIT")
    try:
        requested = int(configured) if configured else DEFAULT_JAMBASE_APP_LIMIT
    except ValueError:
        requested = DEFAULT_JAMBASE_APP_LIMIT
    return min(max(requested, 1), DEFAULT_JAMBASE_APP_LIMIT)


def _current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def reserve_provider_call(
    provider: str,
    call_limit: int,
    db_target: DatabaseTarget = None,
) -> int:
    """Atomically reserve one request before contacting a metered provider."""
    period = _current_period()
    now = datetime.now(timezone.utc)
    with get_connection(db_target) as connection:
        dialect_insert = (
            postgresql_insert if connection.dialect.name == "postgresql" else sqlite_insert
        )
        statement = dialect_insert(provider_api_usage).values(
            provider=provider,
            period=period,
            calls_used=0,
            call_limit=call_limit,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["provider", "period"],
            set_={"call_limit": call_limit, "updated_at": now},
        )
        connection.execute(statement)
        reserved = connection.execute(
            update(provider_api_usage)
            .where(
                provider_api_usage.c.provider == provider,
                provider_api_usage.c.period == period,
                provider_api_usage.c.calls_used < call_limit,
            )
            .values(
                calls_used=provider_api_usage.c.calls_used + 1,
                updated_at=now,
            )
            .returning(provider_api_usage.c.calls_used)
        ).scalar_one_or_none()
        if reserved is None:
            raise ProviderQuotaExceeded(
                f"{provider} monthly application limit of {call_limit} calls reached"
            )
        return int(reserved)


def reserve_jambase_call(db_target: DatabaseTarget = None) -> int:
    return reserve_provider_call("jambase", jambase_monthly_limit(), db_target)


def get_provider_usage(db_target: DatabaseTarget = None) -> list[dict[str, int | str]]:
    with get_connection(db_target) as connection:
        rows = connection.execute(
            select(provider_api_usage).order_by(
                provider_api_usage.c.period.desc(),
                provider_api_usage.c.provider,
            )
        ).mappings()
        return [
            {
                **dict(row),
                "remaining": max(int(row["call_limit"]) - int(row["calls_used"]), 0),
            }
            for row in rows
        ]
