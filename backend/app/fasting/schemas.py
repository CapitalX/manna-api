# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Back-compat schema re-exports.

Phase 16.B3: canonical schemas moved to app.protocols.schemas.
This shim keeps any legacy importers (e.g. old router.py) working.
DELETE in Task 16.C1.
"""
from app.protocols.schemas import (  # noqa: F401
    EatingWindowOverride,
    NutritionTargetsOverride,
    StartProtocolConfig as StartFastRequest,
    UpdateProtocolConfig as UpdateFastRequest,
    UserProtocolResponse as UserFastResponse,
    CompletedDaysResponse,
)
