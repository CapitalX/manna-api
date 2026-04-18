# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Fasting model re-exports.

Phase 16.B2: classes were moved to app.models.protocol and
app.models.user_protocol.  Back-compat aliases keep existing importers
(router.py, conftest.py) working until 16.B3 / 16.B4 update them.
"""
from app.models.protocol import Protocol
from app.models.user_protocol import UserProtocol

# ---------------------------------------------------------------------------
# Back-compat aliases — remove after 16.B3 and 16.B4 land
# ---------------------------------------------------------------------------
FastType = Protocol
UserFast = UserProtocol

__all__ = [
    "Protocol",
    "UserProtocol",
    "FastType",
    "UserFast",
]
