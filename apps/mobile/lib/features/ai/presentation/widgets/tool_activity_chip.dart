import 'package:flutter/material.dart';

import '../../domain/ai_message.dart';

/// One tool the AI called while producing an answer — shown so the Owner
/// can see *how* an answer was reached, not just trust the final text
/// (plan section 16.2's "tool-activity indicators").
class ToolActivityChip extends StatelessWidget {
  const ToolActivityChip({super.key, required this.toolCall});

  final AiToolCall toolCall;

  @override
  Widget build(BuildContext context) {
    return Chip(
      avatar: const Icon(Icons.search, size: 16),
      label: Text(_humanToolName(toolCall.tool)),
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      padding: const EdgeInsets.symmetric(horizontal: 4),
    );
  }
}

String _humanToolName(String tool) {
  return switch (tool) {
    'list_pages' => 'Looking at your tables',
    'get_page_schema' => 'Checking table structure',
    'get_column_values' => 'Checking values',
    'query_records' => 'Reading records',
    'search_records' => 'Searching records',
    'filter_records' => 'Filtering records',
    'sort_records' => 'Sorting records',
    'aggregate_records' => 'Adding up figures',
    'calculate_formula' => 'Calculating',
    'search_entities' => 'Looking up a name',
    'propose_update' => 'Preparing an update',
    'propose_status_change' => 'Preparing a status change',
    _ => tool.replaceAll('_', ' '),
  };
}
