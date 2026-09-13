import '../../../core/date/business_date.dart';

/// One row of `GET /audit-logs` (plan section 18.3, P5). `sentence` is
/// server-formatted (`app/services/audit_read_service.py`) — this client
/// renders it directly rather than rebuilding the human-language
/// description itself.
class AuditLogEntry {
  const AuditLogEntry({
    required this.id,
    required this.createdAt,
    required this.actorName,
    required this.action,
    required this.entityType,
    required this.pageId,
    required this.pageName,
    required this.source,
    required this.sentence,
    required this.oldData,
    required this.newData,
  });

  factory AuditLogEntry.fromJson(Map<String, dynamic> json) {
    return AuditLogEntry(
      id: json['id'] as int,
      createdAt: parseWireDateTime(json['created_at'])!,
      actorName: json['actor_name'] as String?,
      action: json['action'] as String,
      entityType: json['entity_type'] as String,
      pageId: json['page_id'] as String?,
      pageName: json['page_name'] as String?,
      source: json['source'] as String,
      sentence: json['sentence'] as String,
      oldData: json['old_data'] as Map<String, dynamic>?,
      newData: json['new_data'] as Map<String, dynamic>?,
    );
  }

  final int id;

  /// Already company-local wall-clock time (`parseWireDateTime` converts
  /// on the way in) — never the device's own timezone.
  final DateTime createdAt;
  final String? actorName;
  final String action;
  final String entityType;
  final String? pageId;
  final String? pageName;
  final String source;
  final String sentence;
  final Map<String, dynamic>? oldData;
  final Map<String, dynamic>? newData;

  /// "Today" / "Yesterday" / a formatted date, grouped in the company's own
  /// timezone (plan section 18.3's own day-header examples) — the API
  /// deliberately leaves this to the client, since it depends on the
  /// viewer's own local "today", which isn't tracked server-side.
  String get dateHeader {
    final companyNow = toCompanyTime(DateTime.now().toUtc());
    final today = DateTime(companyNow.year, companyNow.month, companyNow.day);
    final entryDay = DateTime(createdAt.year, createdAt.month, createdAt.day);
    final diff = today.difference(entryDay).inDays;
    if (diff == 0) return 'Today';
    if (diff == 1) return 'Yesterday';
    return formatDate(toWireDate(createdAt));
  }
}

class AuditLogFilters {
  const AuditLogFilters({
    this.actorUserId,
    this.pageId,
    this.entityType,
    this.dateFrom,
    this.dateTo,
    this.source,
  });

  final String? actorUserId;
  final String? pageId;
  final String? entityType;
  final DateTime? dateFrom;
  final DateTime? dateTo;
  final String? source;

  Map<String, dynamic> toQueryParameters() => {
    if (actorUserId != null) 'actor_user_id': actorUserId,
    if (pageId != null) 'page_id': pageId,
    if (entityType != null) 'entity_type': entityType,
    if (dateFrom != null) 'date_from': toWireDate(dateFrom!),
    if (dateTo != null) 'date_to': toWireDate(dateTo!),
    if (source != null) 'source': source,
  };
}
