import 'package:flutter/material.dart';

import '../../../domain/column.dart';

/// ATTACHMENT (plan section 10.2) — a count only; the files themselves live
/// behind the `/attachments/*` endpoints, which arrive in P5. Read-only
/// placeholder until then.
class AttachmentFieldRenderer extends StatelessWidget {
  const AttachmentFieldRenderer({super.key, required this.column, required this.value});

  final PageColumn column;
  final Object? value;

  @override
  Widget build(BuildContext context) {
    final count = value is int ? value as int : 0;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const Icon(Icons.attach_file),
      title: Text(column.name),
      subtitle: Text(
        count == 0 ? 'No attachments yet' : '$count attachment${count == 1 ? '' : 's'}',
      ),
      trailing: const Tooltip(
        message: 'Uploading attachments is coming soon',
        child: Icon(Icons.info_outline, size: 18),
      ),
    );
  }
}
