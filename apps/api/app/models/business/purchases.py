"""purchases — a core business table (plan section 8.9 / 12.2).

Purchases made for cash or any other method. Deliberately simple: no quantity,
no unit cost, no item-level lines, no purchase status, no approval or invoice
settlement workflow.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import TIMESTAMP, Date, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BusinessTableMixin


class Purchase(Base, BusinessTableMixin):
    __tablename__ = "purchases"

    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: When the entry was recorded, as opposed to the date the purchase is for.
    entry_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    purchase_name: Mapped[str] = mapped_column(Text, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
