"""expenses — a core business table (plan section 8.9 / 12.3).

Business operating expenses. `expense_name` is free text — "Electricity",
"Rent", "Water", "Repairs", "Transport", "Cleaning", "Internet" — so expense
types are values, never a fixed option list and never separate tables.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import TIMESTAMP, Date, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BusinessTableMixin


class Expense(Base, BusinessTableMixin):
    __tablename__ = "expenses"

    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: When the entry was recorded, as opposed to the date the expense is for.
    entry_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    expense_name: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
