# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Backwards-compat router: /api/v1/fasts/* delegates to /api/v1/protocols/*.

DELETE in Task 16.C1 ~24h after mobile ships Phase 16.
"""
from fastapi import APIRouter

from app.protocols.schemas import UserProtocolResponse, CompletedDaysResponse
from app.protocols.router import (
    start_protocol,
    get_active_protocol,
    complete_protocol,
    abandon_protocol,
    get_protocols,
    update_active_protocol,
    get_completed_days,
    get_recent_protocols,
)

router = APIRouter(prefix="/fasts", tags=["fasts (deprecated)"])

# Mirror each route with the same response_model and status_code as the canonical router.
router.get("/types")(get_protocols)
router.post("/start", response_model=UserProtocolResponse, status_code=201)(start_protocol)
router.get("/me", response_model=UserProtocolResponse)(get_active_protocol)
router.patch("/me", response_model=UserProtocolResponse)(update_active_protocol)
router.post("/me/complete", response_model=UserProtocolResponse)(complete_protocol)
router.post("/me/abandon", response_model=UserProtocolResponse)(abandon_protocol)
router.get("/me/completed-days", response_model=CompletedDaysResponse)(get_completed_days)
router.get("/me/recent", response_model=list[UserProtocolResponse])(get_recent_protocols)
