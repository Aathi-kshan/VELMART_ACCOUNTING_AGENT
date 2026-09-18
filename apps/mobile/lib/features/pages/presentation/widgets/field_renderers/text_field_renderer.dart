import 'package:flutter/material.dart';

import '../../../domain/column.dart';

/// TEXT and LONG_TEXT (plan section 10.2): a single-line or multiline field,
/// bounded at the server's own limits (500 / 10,000 chars) so a form never
/// lets someone type past what the server will accept.
class TextFieldRenderer extends StatelessWidget {
  const TextFieldRenderer({
    super.key,
    required this.column,
    required this.value,
    required this.onChanged,
    this.enabled = true,
    this.errorText,
  });

  final PageColumn column;
  final String? value;
  final ValueChanged<Object?> onChanged;
  final bool enabled;
  final String? errorText;

  bool get _isLong => column.dataType == ColumnType.longText;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      initialValue: value,
      enabled: enabled,
      maxLength: _isLong ? 10000 : 500,
      maxLines: _isLong ? 5 : 1,
      decoration: InputDecoration(
        labelText: column.isRequired ? '${column.name} *' : column.name,
        errorText: errorText,
        helperText: column.description,
      ),
      validator: (input) {
        if (column.isRequired && (input == null || input.trim().isEmpty)) {
          return '${column.name} is required';
        }
        return null;
      },
      onChanged: (input) => onChanged(input.isEmpty ? null : input),
    );
  }
}
