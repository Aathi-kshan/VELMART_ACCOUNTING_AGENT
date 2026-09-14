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
      avatar: const Icon(Icons.bolt, size: 16),
      label: Text('${toolCall.tool.replaceAll('_', ' ')} · ${toolCall.durationMs}ms'),
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      padding: const EdgeInsets.symmetric(horizontal: 4),
    );
  }
}
