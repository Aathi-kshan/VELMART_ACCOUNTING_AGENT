/// The Owner-only AI chat (plan section 16, P7.6/P7.12/P8 Lite; docs/API.md
/// §9). `proposal` is populated whenever the AI called `propose_update`/
/// `propose_status_change` while answering — it never writes business data
/// itself, only prepares this for the Owner's review.
library;

/// Where a stated figure came from — page, how many records, what date
/// range. Computed server-side (`app/ai/provenance.py`), never invented by
/// the model; rendered under an assistant message that carries one.
class AiProvenance {
  const AiProvenance({
    required this.page,
    required this.recordCount,
    required this.dateFrom,
    required this.dateTo,
  });

  factory AiProvenance.fromJson(Map<String, dynamic> json) {
    return AiProvenance(
      page: json['page'] as String,
      recordCount: json['record_count'] as int,
      dateFrom: json['from'] as String?,
      dateTo: json['to'] as String?,
    );
  }

  final String page;
  final int recordCount;
  final String? dateFrom;
  final String? dateTo;

  String get summary {
    if (dateFrom == null) return '$recordCount record(s) in $page';
    return '$recordCount record(s) in $page, $dateFrom to $dateTo';
  }
}

/// One tool the AI called while answering — shown as an activity chip so
/// the Owner can see how an answer was produced, not just the answer.
class AiToolCall {
  const AiToolCall({required this.tool, required this.durationMs});

  factory AiToolCall.fromJson(Map<String, dynamic> json) {
    return AiToolCall(tool: json['tool'] as String, durationMs: json['duration_ms'] as int);
  }

  final String tool;
  final int durationMs;
}

/// One field the AI is proposing to change — `before`/`after` come through
/// as whatever wire type the column already uses (a money string, a plain
/// number, a bool), so this stays `dynamic` and only formats for display.
class AiProposalChange {
  const AiProposalChange({required this.column, required this.before, required this.after});

  factory AiProposalChange.fromJson(Map<String, dynamic> json) {
    return AiProposalChange(
      column: json['column'] as String,
      before: json['before'],
      after: json['after'],
    );
  }

  final String column;
  final dynamic before;
  final dynamic after;

  String get beforeDisplay => before == null ? '—' : before.toString();
  String get afterDisplay => after == null ? '—' : after.toString();
}

/// A pending change the AI has prepared — never applied until the Owner
/// taps Update. The server computed `changes` from the real database, not
/// from anything the AI assumed (plan section "Standing design decisions").
class AiProposal {
  const AiProposal({
    required this.id,
    required this.summary,
    required this.expiresAt,
    required this.page,
    required this.changes,
  });

  factory AiProposal.fromJson(Map<String, dynamic> json) {
    return AiProposal(
      id: json['id'] as String,
      summary: json['summary'] as String,
      expiresAt: DateTime.parse(json['expires_at'] as String),
      page: json['page'] as String,
      changes: (json['changes'] as List<dynamic>)
          .map((e) => AiProposalChange.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  final String id;
  final String summary;
  final DateTime expiresAt;
  final String page;
  final List<AiProposalChange> changes;

  /// "Expires in N minutes" — computed client-side from the real
  /// `expires_at`, never guessed; goes negative once past it, so callers
  /// should prefer [isExpired] to decide what to render.
  Duration get timeRemaining => expiresAt.difference(DateTime.now());

  bool get isExpired => timeRemaining.isNegative;

  String get expiryLabel {
    if (isExpired) return 'Expired';
    final minutes = timeRemaining.inMinutes;
    if (minutes < 1) return 'Expires in under a minute';
    return 'Expires in $minutes minute${minutes == 1 ? '' : 's'}';
  }
}

enum AiMessageRole { user, assistant }

/// One message in the current chat — either what the Owner typed, or the
/// assistant's response (with its tool activity and provenance, if any).
class AiChatMessage {
  const AiChatMessage({
    required this.role,
    required this.content,
    this.provenance = const [],
    this.toolCalls = const [],
    this.proposal,
    this.costUsd,
    this.partial = false,
  });

  factory AiChatMessage.user(String content) =>
      AiChatMessage(role: AiMessageRole.user, content: content);

  factory AiChatMessage.fromResponseJson(Map<String, dynamic> json) {
    final proposalJson = json['proposal'] as Map<String, dynamic>?;
    return AiChatMessage(
      role: AiMessageRole.assistant,
      content: json['answer'] as String,
      provenance: (json['provenance'] as List<dynamic>? ?? const [])
          .map((e) => AiProvenance.fromJson(e as Map<String, dynamic>))
          .toList(),
      toolCalls: (json['tool_calls'] as List<dynamic>? ?? const [])
          .map((e) => AiToolCall.fromJson(e as Map<String, dynamic>))
          .toList(),
      proposal: proposalJson == null ? null : AiProposal.fromJson(proposalJson),
      costUsd: json['cost_usd'] as String?,
      partial: json['partial'] as bool? ?? false,
    );
  }

  final AiMessageRole role;
  final String content;
  final List<AiProvenance> provenance;
  final List<AiToolCall> toolCalls;
  final AiProposal? proposal;
  final String? costUsd;
  final bool partial;
}
