# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Shim smoke tests: /api/v1/fasts/* must delegate to /api/v1/protocols/*.

These tests verify that the backwards-compat shim (app/fasting/shim.py)
mirrors the canonical /protocols/* routes.  They should PASS once 16.B3
is complete and CONTINUE passing until the shim is deleted in 16.C1.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import create_user_and_token, seed_fast_types

pytestmark = pytest.mark.asyncio


class TestFastsShimDelegation:
    async def test_shim_get_types_matches_protocols_types(
        self, client, db_session: AsyncSession
    ):
        """GET /fasts/types returns the same body as GET /protocols/types."""
        await seed_fast_types(db_session)
        r_new = client.get("/api/v1/protocols/types")
        r_shim = client.get("/api/v1/fasts/types")
        assert r_new.status_code == r_shim.status_code == 200
        assert r_new.json() == r_shim.json()

    async def test_shim_me_404_matches_protocols_me_404(
        self, authed_client, db_session: AsyncSession
    ):
        """GET /fasts/me == GET /protocols/me (both 404, same detail) when no active protocol."""
        client, state = authed_client
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        r_new = client.get("/api/v1/protocols/me")
        r_shim = client.get("/api/v1/fasts/me")
        assert r_new.status_code == r_shim.status_code
        assert r_new.json() == r_shim.json()

    async def test_shim_completed_days_matches_protocols(
        self, authed_client, db_session: AsyncSession
    ):
        """GET /fasts/me/completed-days == GET /protocols/me/completed-days."""
        client, state = authed_client
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        r_new = client.get("/api/v1/protocols/me/completed-days")
        r_shim = client.get("/api/v1/fasts/me/completed-days")
        assert r_new.status_code == r_shim.status_code == 200
        assert r_new.json() == r_shim.json()

    async def test_shim_start_and_get_active(
        self, authed_client, db_session: AsyncSession
    ):
        """POST /fasts/start creates protocol; GET /protocols/me returns it."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        # Start via shim
        r_start = client.post("/api/v1/fasts/start", json={"fast_type_id": "daniel_fast"})
        assert r_start.status_code == 201

        # Read back via canonical protocols route
        r_canonical = client.get("/api/v1/protocols/me")
        assert r_canonical.status_code == 200
        assert r_canonical.json()["fast_type_id"] == "daniel_fast"

    async def test_shim_patch_me_update_applies(
        self, authed_client, db_session: AsyncSession
    ):
        """PATCH /fasts/me (shim) updates eating_window_override; canonical GET reflects it."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"fast_type_id": "if_16_8"})
        r_patch = client.patch(
            "/api/v1/fasts/me",
            json={"eating_window_override": {"start_time": "09:00", "end_time": "17:00"}},
        )
        assert r_patch.status_code == 200

        r_canonical = client.get("/api/v1/protocols/me")
        assert r_canonical.json()["eating_window_override"] == {
            "start_time": "09:00",
            "end_time": "17:00",
        }

    async def test_shim_complete_via_fasts_route(
        self, authed_client, db_session: AsyncSession
    ):
        """POST /fasts/me/complete (shim) marks protocol completed; canonical GET confirms."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"fast_type_id": "daniel_fast"})
        r_complete = client.post("/api/v1/fasts/me/complete")
        assert r_complete.status_code == 200
        assert r_complete.json()["status"] == "completed"

    async def test_shim_abandon_via_fasts_route(
        self, authed_client, db_session: AsyncSession
    ):
        """POST /fasts/me/abandon (shim) marks protocol abandoned; status confirmed."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        client.post("/api/v1/protocols/start", json={"fast_type_id": "daniel_fast"})
        r_abandon = client.post("/api/v1/fasts/me/abandon")
        assert r_abandon.status_code == 200
        assert r_abandon.json()["status"] == "abandoned"

    async def test_shim_recent_matches_protocols_recent(
        self, authed_client, db_session: AsyncSession
    ):
        """GET /fasts/me/recent (shim) returns same list as /protocols/me/recent."""
        client, state = authed_client
        await seed_fast_types(db_session)
        user, _ = await create_user_and_token(db_session)
        state["user"] = user

        # Complete a protocol via canonical route so there's something to list
        client.post("/api/v1/protocols/start", json={"fast_type_id": "daniel_fast"})
        client.post("/api/v1/protocols/me/complete")

        r_canonical = client.get("/api/v1/protocols/me/recent")
        r_shim = client.get("/api/v1/fasts/me/recent")
        assert r_canonical.status_code == r_shim.status_code == 200
        assert r_canonical.json() == r_shim.json()
