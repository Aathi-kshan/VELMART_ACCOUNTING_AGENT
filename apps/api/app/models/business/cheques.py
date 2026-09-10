"""cheques — a core business table (plan section 8.9 / 12.6).

`status` is the protected column: managers may create cheque records but cannot
change the status of an existing one. Only the Owner sets PENDING -> PAID,
through the protected-field endpoint, audited as PROTECTED_FIELD_CHANGE.
There is no separate cheque approval workflow.
"""

from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BusinessTableMixin


class ChequeStatus(enum.StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"


class Cheque(Base, BusinessTableMixin):
    __tablename__ = "cheques"

    cheque_number: Mapped[str] = mapped_column(Text, nullable=False)
    #: Payee / supplier as free text: no suppliers table ships.
    payee_name: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cheque_date: Mapped[date | None] = mapped_column(Date)
    #: The protected business status, shown to the Owner as "Status". Named
    #: cheque_status because `status` is already the platform record lifecycle
    #: (ACTIVE/REVERSED/VOID) carried by BusinessTableMixin.
    cheque_status: Mapped[ChequeStatus] = mapped_column(
        SAEnum(ChequeStatus, name="cheque_status", create_type=False),
        nullable=False,
        server_default=ChequeStatus.PENDING.value,
    )
    reference: Mapped[str | None] = mapped_column(Text)
