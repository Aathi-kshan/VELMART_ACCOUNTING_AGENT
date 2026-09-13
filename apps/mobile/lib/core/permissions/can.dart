/// UI hints only, mirroring the unambiguous (non-🟡) rows of plan section
/// 4.2 — every one of these is `role == UserRole.owner`, and only decides
/// which buttons and screens the manager sees. The real gate for every one
/// of these actions is the matching FastAPI endpoint (`app/core/permissions.py`,
/// enforced by `test_permissions_matrix`), never this file: "Flutter hides
/// buttons; Flutter never decides anything" (routing/guards.dart).
///
/// `GET /stores`'s manager-sees-only-assigned filtering (the 🟡 row) has no
/// helper here on purpose — it isn't a yes/no permission, it's server-side
/// data scoping, and the client just renders whatever the API returns.
library;

import '../../features/auth/domain/user.dart';

bool canEditRecord(UserRole role) => role == UserRole.owner;

bool canDeleteRecord(UserRole role) => role == UserRole.owner;

bool canSetProtectedField(UserRole role) => role == UserRole.owner;

bool canCreatePage(UserRole role) => role == UserRole.owner;

bool canManageColumns(UserRole role) => role == UserRole.owner;

bool canExportCsv(UserRole role) => role == UserRole.owner;

bool canUseAi(UserRole role) => role == UserRole.owner;

bool canManageUsers(UserRole role) => role == UserRole.owner;

bool canManageStores(UserRole role) => role == UserRole.owner;

bool canManageSettings(UserRole role) => role == UserRole.owner;

bool canExportAuditLog(UserRole role) => role == UserRole.owner;
