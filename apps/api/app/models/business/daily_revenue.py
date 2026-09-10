"""daily_revenue — a core business table (plan section 8.9 / 12.4).

    Total Revenue = Cash Sales + Card Sales

Computed by the database in NUMERIC (Decimal), never by the application, so it
cannot disagree with its inputs. Reconciled against `cash_ledger` for the same
business date through the `daily_reconciliation` view.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Computed, Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BusinessTableMixin


class DailyRevenue(Base, BusinessTableMixin):
    __tablename__ = "daily_revenue"

    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    cash_sales: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    card_sales: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    total_revenue: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), Computed("cash_sales + card_sales", persisted=True)
    )
