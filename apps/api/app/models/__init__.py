"""Import every model so it registers on Base.metadata (used by Alembic env.py)."""

from app.models.ai import AiMessage, AiProposal, AiProposalItem, AiSession, ProposalStatus
from app.models.attachment import Attachment
from app.models.audit import AuditAction, AuditLog
from app.models.business import (
    RESERVED_PAGE_KEYS,
    SYSTEM_PAGE_KEYS,
    CashLedger,
    Cheque,
    ChequeStatus,
    DailyRevenue,
    EmployeeSalary,
    Expense,
    Purchase,
)
from app.models.company import Company, CompanySettings
from app.models.daily_digest import DailyDigest
from app.models.page import Page, PageKind
from app.models.page_access import PageAccess
from app.models.page_column import ColumnType, PageColumn
from app.models.rate_limit import RateLimit
from app.models.record import Record, RecordStatus
from app.models.store import Store
from app.models.user import IdempotencyKey, RefreshToken, User, UserRole, UserStore

__all__ = [
    "AiMessage",
    "AiProposal",
    "AiProposalItem",
    "AiSession",
    "ProposalStatus",
    "Attachment",
    "AuditAction",
    "AuditLog",
    "SYSTEM_PAGE_KEYS",
    "RESERVED_PAGE_KEYS",
    "CashLedger",
    "Cheque",
    "ChequeStatus",
    "DailyRevenue",
    "EmployeeSalary",
    "Expense",
    "Purchase",
    "Company",
    "CompanySettings",
    "DailyDigest",
    "Page",
    "PageKind",
    "PageAccess",
    "ColumnType",
    "PageColumn",
    "RateLimit",
    "Record",
    "RecordStatus",
    "Store",
    "IdempotencyKey",
    "RefreshToken",
    "User",
    "UserRole",
    "UserStore",
]
