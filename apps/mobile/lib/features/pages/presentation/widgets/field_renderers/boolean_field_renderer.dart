import 'package:flutter/material.dart';

import '../../../domain/column.dart';

/// BOOLEAN (plan section 10.2) — a real JSON boolean on the wire, never a
/// string. A switch, not a dropdown, since yes/no is the whole domain.
class BooleanFieldRenderer extends StatelessWidget {
  const BooleanFieldRenderer({
    super.key,
    required this.column,
    required this.value,
    required this.onChanged,
    this.enabled = true,
  });

  final PageColumn column;
  final bool? value;
  final ValueChanged<Object?> onChanged;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      title: Text(column.name),
      subtitle: column.description != null ? Text(column.description!) : null,
      value: value ?? false,
      onChanged: enabled ? (next) => onChanged(next) : null,
      contentPadding: EdgeInsets.zero,
    );
  }
}
