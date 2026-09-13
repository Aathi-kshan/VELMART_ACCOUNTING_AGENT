"""SecurityContext — the one source of tenancy for an authenticated request.

Built once, right after the JWT is decoded (see app/dependencies/auth.py), and
carried through the request. Deliberately does NOT cache page grants
(plan section 20.2): those are read fresh per request, so a revoked grant
takes effect immediately rather than surviving until the token expires.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.user import UserRole


@dataclass(frozen=True, slots=True)
class SecurityContext:
    user_id: uuid.UUID
    company_id: uuid.UUID
    role: UserRole
    store_ids: tuple[uuid.UUID, ...]

    @property
    def is_owner(self) -> bool:
        return self.role == UserRole.OWNER
