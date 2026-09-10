"""employee_salaries — a core business table (plan section 8.9 / 12.1).

One record is one salary payment. Deliberately minimal: no basic salary, OT,
bonus, allowances, deductions, net salary, payment status or payment method.
Those are only added if explicitly required later.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BusinessTableMixin


class EmployeeSalary(Base, BusinessTableMixin):
    __tablename__ = "employee_salaries"

    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    # TEXT, not a reference: no employees table ships. Upgrades to employee_id
    # UUID if the Owner later needs one.
    employee_name: Mapped[str] = mapped_column(Text, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(Text)
