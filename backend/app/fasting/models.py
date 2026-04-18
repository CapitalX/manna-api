# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Fasting model re-exports.

Phase 16.B2: classes were moved to app.models.protocol and
app.models.user_protocol.  Back-compat aliases keep existing importers
(conftest.py, shim.py) working until the shim is deleted in 16.C1.
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
