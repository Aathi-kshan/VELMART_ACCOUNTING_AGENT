/// The Owner-only AI chat (plan section 16, P7.6/P7.12; docs/API.md §9).
/// `proposal` is always `null` in this phase — parsed so the shape is
/// stable once P8 starts populating it, never rendered before then.
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

enum AiMessageRole { user, assistant }

/// One message in the current chat — either what the Owner typed, or the
/// assistant's response (with its tool activity and provenance, if any).
class AiChatMessage {
  const AiChatMessage({
    required this.role,
    required this.content,
    this.provenance = const [],
    this.toolCalls = const [],
    this.costUsd,
    this.partial = false,
  });

  factory AiChatMessage.user(String content) =>
      AiChatMessage(role: AiMessageRole.user, content: content);

  factory AiChatMessage.fromResponseJson(Map<String, dynamic> json) {
    return AiChatMessage(
      role: AiMessageRole.assistant,
      content: json['answer'] as String,
      provenance: (json['provenance'] as List<dynamic>? ?? const [])
          .map((e) => AiProvenance.fromJson(e as Map<String, dynamic>))
          .toList(),
      toolCalls: (json['tool_calls'] as List<dynamic>? ?? const [])
          .map((e) => AiToolCall.fromJson(e as Map<String, dynamic>))
          .toList(),
      costUsd: json['cost_usd'] as String?,
      partial: json['partial'] as bool? ?? false,
    );
  }

  final AiMessageRole role;
  final String content;
  final List<AiProvenance> provenance;
  final List<AiToolCall> toolCalls;
  final String? costUsd;
  final bool partial;
}
