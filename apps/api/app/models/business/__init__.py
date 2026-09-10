"""The six core business tables (plan section 8.9 / 12).

Employee Salary · Purchases · Expenses · Daily Revenue · Cash Ledger · Cheques.

Each is registered as a system page in `pages` (is_system=true, storage_table
set) so the generic page-engine surface works over it unchanged. See ADR 0006.
No further business tables ship: a seventh domain is an Owner-created page.
"""

from app.models.business.cash_ledger import CashLedger
from app.models.business.cheques import Cheque, ChequeStatus
from app.models.business.daily_revenue import DailyRevenue
from app.models.business.employee_salary import EmployeeSalary
from app.models.business.expenses import Expense
from app.models.business.purchases import Purchase

#: Canonical page key -> backing table name.
SYSTEM_PAGE_KEYS: dict[str, str] = {
    "employee_salary": "employee_salaries",
    "purchases": "purchases",
    "expenses": "expenses",
    "daily_revenue": "daily_revenue",
    "cash_ledger": "cash_ledger",
    "cheques": "cheques",
}

#: Keys the page engine refuses for Owner-created pages (409 RESERVED_PAGE_KEY).
#: Includes singular/plural variants so "Cheque" cannot slip past "cheques" and
#: quietly become a second source of truth for the same records.
RESERVED_PAGE_KEYS: frozenset[str] = frozenset(SYSTEM_PAGE_KEYS) | frozenset(
    {
        "employee_salaries",
        "employee_salaries_page",
        "salary",
        "salaries",
        "purchase",
        "buying_for_cash",
        "expense",
        "revenue",
        "daily_revenues",
        "cash_ledgers",
        "cheque",
    }
)

__all__ = [
    "CashLedger",
    "Cheque",
    "ChequeStatus",
    "DailyRevenue",
    "EmployeeSalary",
    "Expense",
    "Purchase",
    "SYSTEM_PAGE_KEYS",
    "RESERVED_PAGE_KEYS",
]
