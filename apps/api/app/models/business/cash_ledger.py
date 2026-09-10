"""cash_ledger — a core business table (plan section 8.9 / 12.5).

    Total Amount = Cash Amount + Card Sales Amount

Recorded daily and reconciled against `daily_revenue` for the same business
date. A zero difference means the two totals match:

    Difference = Daily Revenue total_revenue - Cash Ledger total_amount

That comparison is the `daily_reconciliation` view, created in migration 0008.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Computed, Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BusinessTableMixin


class CashLedger(Base, BusinessTableMixin):
    __tablename__ = "cash_ledger"

    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    cash_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    card_sales_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), Computed("cash_amount + card_sales_amount", persisted=True)
    )
