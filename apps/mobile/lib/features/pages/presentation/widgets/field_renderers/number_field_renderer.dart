import 'package:flutter/material.dart';

import '../../../domain/column.dart';

/// NUMBER and PERCENT (plan section 10.2). The value stays a wire-format
/// string end to end — the server parses it as `Decimal`; this widget only
/// checks it looks like a number and respects `config.min`/`max`.
class NumberFieldRenderer extends StatelessWidget {
  const NumberFieldRenderer({
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

  bool get _isPercent => column.dataType == ColumnType.percent;

  @override
  Widget build(BuildContext context) {
    final min = double.tryParse(column.minValue ?? (_isPercent ? '0' : ''));
    final max = double.tryParse(column.maxValue ?? (_isPercent ? '100' : ''));

    return TextFormField(
      initialValue: value,
      enabled: enabled,
      textAlign: TextAlign.end,
      keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
      decoration: InputDecoration(
        labelText: column.isRequired ? '${column.name} *' : column.name,
        suffixText: _isPercent ? '%' : null,
        errorText: errorText,
        helperText: column.description,
      ),
      validator: (input) {
        if (column.isRequired && (input == null || input.trim().isEmpty)) {
          return '${column.name} is required';
        }
        if (input == null || input.trim().isEmpty) return null;
        final parsed = double.tryParse(input);
        if (parsed == null) return 'Enter a valid number';
        if (min != null && parsed < min) return 'Must be at least $min';
        if (max != null && parsed > max) return 'Must be at most $max';
        return null;
      },
      onChanged: (input) => onChanged(input.isEmpty ? null : input),
    );
  }
}
