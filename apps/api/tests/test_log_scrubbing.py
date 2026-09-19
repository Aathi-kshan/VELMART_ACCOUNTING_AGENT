"""Sensitive values must not reach the log, at any depth.

`_scrub` walked only the event dict's own keys. Anything nested slipped
straight through — `{"record": {"data": {...}}}` logged every business value
the `data` entry exists to redact, and an error context carrying
`{"payload": {"password": ...}}` logged the password. Nesting is the normal
shape of anything interesting enough to log, so the shallow version redacted
mainly the cases that were already obvious.

The key list was also short on personal data: no `email`, `phone`, `nic`
(Sri Lankan national identity card) or `cookie`.
"""

from __future__ import annotations

from app.core.logging import REDACTED, _scrub


def scrub(event: dict) -> dict:
    return _scrub(None, "info", event)


class TestTopLevelRedaction:
    def test_known_keys_are_redacted(self) -> None:
        out = scrub({"event": "x", "password": "hunter2", "access_token": "abc"})
        assert out["password"] == REDACTED
        assert out["access_token"] == REDACTED
        assert out["event"] == "x"

    def test_matching_is_case_insensitive(self) -> None:
        assert scrub({"Authorization": "Bearer x"})["Authorization"] == REDACTED

    def test_ordinary_values_are_untouched(self) -> None:
        out = scrub({"event": "request.completed", "status_code": 200, "duration_ms": 12.5})
        assert out["status_code"] == 200
        assert out["duration_ms"] == 12.5


class TestNestedRedaction:
    def test_a_nested_record_payload_is_redacted(self) -> None:
        out = scrub({"event": "x", "record": {"id": "r1", "data": {"amount": "999999.00"}}})
        assert out["record"]["data"] == REDACTED
        assert out["record"]["id"] == "r1", "non-sensitive siblings must survive"

    def test_a_deeply_nested_password_is_redacted(self) -> None:
        out = scrub({"ctx": {"request": {"body": {"password": "hunter2"}}}})
        assert out["ctx"]["request"]["body"]["password"] == REDACTED

    def test_sensitive_keys_inside_a_list_are_redacted(self) -> None:
        out = scrub({"users": [{"email": "a@b.lk"}, {"email": "c@d.lk"}]})
        assert [u["email"] for u in out["users"]] == [REDACTED, REDACTED]

    def test_runaway_nesting_is_bounded(self) -> None:
        """A cycle or a pathological structure must not hang the logger."""
        deep: dict = {"k": "v"}
        for _ in range(30):
            deep = {"nested": deep}
        assert scrub(deep) is not None


class TestPersonalDataKeys:
    def test_personal_identifiers_are_redacted(self) -> None:
        out = scrub(
            {
                "email": "owner@velmart.lk",
                "phone": "0771234567",
                "nic": "199012345678",
                "full_name": "A. Perera",
                "cookie": "session=abc",
            }
        )
        assert all(v == REDACTED for v in out.values()), out

    def test_audit_payloads_are_redacted(self) -> None:
        """`old_data`/`new_data`/`diff` carry the same business values as
        `data`, which was already on the list."""
        out = scrub({"old_data": {"amount": "1.00"}, "new_data": {"amount": "2.00"}, "diff": {}})
        assert out["old_data"] == REDACTED
        assert out["new_data"] == REDACTED
        assert out["diff"] == REDACTED
