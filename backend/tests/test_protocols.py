# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Tests for the /api/v1/protocols endpoints (canonical routes).

TDD approach — tests define expected behaviour. Uses SQLite in-memory DB
via authed_client fixture which bypasses PG-specific set_config calls.
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    create_user_and_token,
    seed_fast_types,
    ALL_FAST_TYPES_SEEDS,
)
from app.models.user import User

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# GET /protocols/types  (no auth required — uses plain `client`)
# ---------------------------------------------------------------------------

class TestGetProtocolTypes:
    async def test_returns_all_active_protocol_types(
        self, client: TestClient, db_session: AsyncSession
    ):
        """GET /protocols/types returns all 7 active protocol types."""
        await seed_fast_types(db_session)
        response = client.get("/api/v1/protocols/types")
        assert response.status_code == 200
        assert len(response.json()) == 7

    async def test_returns_protocol_type_fields(
        self, client: TestClient, db_session: AsyncSession
    ):
        """Each protocol type contains the expected top-level fields."""
        await seed_fast_types(db_session)
        data = client.get("/api/v1/protocols/types").json()
        first = next(ft for ft in data if ft["id"] == "daniel_fast")
        assert first["name"] == "Daniel Fast"
        assert first["category"] == "faith"
        assert "duration" in first
        assert "eating_window" in first
        assert "streak_tracking" in first

    async def test_no_auth_required(
        self, client: TestClient, db_session: AsyncSession
    ):
        """No Authorization header needed."""
        await seed_fast_types(db_session)
        response = client.get("/api/v1/protocols/types")
        assert response.status_code == 200

    async def test_empty_when_no_protocol_types(
        self, client: TestClient, db_session: AsyncSession
    ):
        """Empty list when no protocol types seeded."""
        assert client.get("/api/v1/protocols/types").json() == []


# ---------------------------------------------------------------------------
# POST /protocols/start
# ---------------------------------------------------------------------------

class TestStartProtocol:
    async def test_creates_user_protocol(
        self, authed_client, db_session: AsyncSession
    ):
        """POST /protocols/start → 201 with UserProtocol response."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.post(
            "/api/v1/protocols/start",
            json={"protocol_id": "daniel_fast"},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["protocol_id"] == "daniel_fast"
        assert data["status"] == "active"
        assert data["current_day"] == 1
        assert data["start_date"] == date.today().isoformat()

    async def test_409_when_active_protocol_exists(
        self, authed_client, db_session: AsyncSession
    ):
        """409 when user already has an active protocol."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"protocol_id": "daniel_fast"})
        response = client.post("/api/v1/protocols/start", json={"protocol_id": "daniel_fast"})
        assert response.status_code == 409

    async def test_422_custom_duration_below_min(
        self, authed_client, db_session: AsyncSession
    ):
        """422 when custom_duration_days < min_days (min=1 for daniel_fast)."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.post(
            "/api/v1/protocols/start",
            json={"protocol_id": "daniel_fast", "custom_duration_days": 0},
        )
        assert response.status_code == 422

    async def test_422_custom_duration_above_max(
        self, authed_client, db_session: AsyncSession
    ):
        """422 when custom_duration_days > max_days (max=40 for daniel_fast)."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.post(
            "/api/v1/protocols/start",
            json={"protocol_id": "daniel_fast", "custom_duration_days": 99},
        )
        assert response.status_code == 422

    async def test_422_custom_duration_on_fixed_type(
        self, authed_client, db_session: AsyncSession
    ):
        """422 when custom_duration_days set for fixed-duration protocol (esther_fast)."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.post(
            "/api/v1/protocols/start",
            json={"protocol_id": "esther_fast", "custom_duration_days": 2},
        )
        assert response.status_code == 422

    async def test_404_unknown_protocol_type(
        self, authed_client, db_session: AsyncSession
    ):
        """404 when protocol_id doesn't match any active protocol type."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.post(
            "/api/v1/protocols/start",
            json={"protocol_id": "nonexistent_fast"},
        )
        assert response.status_code == 404

    async def test_fixed_type_sets_correct_end_date(
        self, authed_client, db_session: AsyncSession
    ):
        """Esther Fast (3-day fixed): end_date = start + 3 days."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.post("/api/v1/protocols/start", json={"protocol_id": "esther_fast"})
        assert response.status_code == 201
        expected_end = (date.today() + timedelta(days=3)).isoformat()
        assert response.json()["end_date"] == expected_end

    async def test_ongoing_type_has_null_end_date(
        self, authed_client, db_session: AsyncSession
    ):
        """Ongoing IF protocols have end_date = null."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.post("/api/v1/protocols/start", json={"protocol_id": "if_16_8"})
        assert response.status_code == 201
        assert response.json()["end_date"] is None

    async def test_stores_eating_window_override(
        self, authed_client, db_session: AsyncSession
    ):
        """eating_window_override is stored and returned in the response."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.post(
            "/api/v1/protocols/start",
            json={
                "protocol_id": "if_16_8",
                "eating_window_override": {"start_time": "10:00", "end_time": "18:00"},
            },
        )
        assert response.status_code == 201
        assert response.json()["eating_window_override"] == {
            "start_time": "10:00",
            "end_time": "18:00",
        }

    async def test_401_when_not_authenticated(
        self, client: TestClient, db_session: AsyncSession
    ):
        """403/401 without Bearer token (HTTPBearer returns 403)."""
        await seed_fast_types(db_session)
        response = client.post(
            "/api/v1/protocols/start",
            json={"protocol_id": "daniel_fast"},
        )
        # FastAPI HTTPBearer returns 403 for missing credentials
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /protocols/me
# ---------------------------------------------------------------------------

class TestGetActiveProtocol:
    async def test_returns_active_protocol(
        self, authed_client, db_session: AsyncSession
    ):
        """GET /protocols/me returns the user's active protocol."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"protocol_id": "daniel_fast"})
        response = client.get("/api/v1/protocols/me")
        assert response.status_code == 200
        assert response.json()["protocol_id"] == "daniel_fast"
        assert response.json()["status"] == "active"

    async def test_404_when_no_active_protocol(
        self, authed_client, db_session: AsyncSession
    ):
        """GET /protocols/me → 404 when user has no active protocol."""
        client, state = authed_client
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.get("/api/v1/protocols/me")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /protocols/me/complete  &  POST /protocols/me/abandon
# ---------------------------------------------------------------------------

class TestProtocolStateTransitions:
    async def test_complete_protocol(
        self, authed_client, db_session: AsyncSession
    ):
        """POST /protocols/me/complete → status becomes 'completed'."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"protocol_id": "daniel_fast"})
        response = client.post("/api/v1/protocols/me/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    async def test_complete_clears_active_protocol(
        self, authed_client, db_session: AsyncSession
    ):
        """After completing, GET /protocols/me returns 404."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"protocol_id": "daniel_fast"})
        client.post("/api/v1/protocols/me/complete")
        assert client.get("/api/v1/protocols/me").status_code == 404

    async def test_abandon_protocol(
        self, authed_client, db_session: AsyncSession
    ):
        """POST /protocols/me/abandon → status becomes 'abandoned'."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"protocol_id": "daniel_fast"})
        response = client.post("/api/v1/protocols/me/abandon")
        assert response.status_code == 200
        assert response.json()["status"] == "abandoned"

    async def test_complete_404_when_no_active_protocol(
        self, authed_client, db_session: AsyncSession
    ):
        """POST /protocols/me/complete → 404 when no active protocol."""
        client, state = authed_client
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        assert client.post("/api/v1/protocols/me/complete").status_code == 404

    async def test_abandon_404_when_no_active_protocol(
        self, authed_client, db_session: AsyncSession
    ):
        """POST /protocols/me/abandon → 404 when no active protocol."""
        client, state = authed_client
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        assert client.post("/api/v1/protocols/me/abandon").status_code == 404


# ---------------------------------------------------------------------------
# GET /protocols/me/completed-days
# ---------------------------------------------------------------------------

class TestCompletedDays:
    async def test_returns_empty_when_no_completed_protocols(
        self, authed_client, db_session: AsyncSession
    ):
        """Returns empty list when user has never completed a protocol."""
        client, state = authed_client
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        response = client.get("/api/v1/protocols/me/completed-days")
        assert response.status_code == 200
        assert response.json()["completed_days"] == []

    async def test_returns_iso_dates_after_completing(
        self, authed_client, db_session: AsyncSession
    ):
        """Returns today's ISO date after completing a protocol."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"protocol_id": "daniel_fast"})
        client.post("/api/v1/protocols/me/complete")

        response = client.get("/api/v1/protocols/me/completed-days")
        assert response.status_code == 200
        days = response.json()["completed_days"]
        assert len(days) >= 1
        assert date.today().isoformat() in days

    async def test_abandoned_not_in_completed_days(
        self, authed_client, db_session: AsyncSession
    ):
        """Abandoned protocols do NOT appear in completed_days."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"protocol_id": "daniel_fast"})
        client.post("/api/v1/protocols/me/abandon")

        response = client.get("/api/v1/protocols/me/completed-days")
        assert response.json()["completed_days"] == []
