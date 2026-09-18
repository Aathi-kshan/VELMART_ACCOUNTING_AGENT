import 'package:flutter/material.dart';

import '../../../../../core/money/money.dart';
import '../../../domain/column.dart';

/// CURRENCY (plan sections 9.1, 10.2). Money crosses the wire as a string
/// and is parsed here only for validation — the value handed back through
/// `onChanged` stays a string, never a `double` (`Money` itself is `int`
/// minor units for exactly this reason).
class CurrencyFieldRenderer extends StatelessWidget {
  const CurrencyFieldRenderer({
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

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      initialValue: value,
      enabled: enabled,
      textAlign: TextAlign.end,
      keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
      decoration: InputDecoration(
        labelText: column.isRequired ? '${column.name} *' : column.name,
        prefixText: 'Rs. ',
        errorText: errorText,
        helperText: column.description,
      ),
      validator: (input) {
        if (column.isRequired && (input == null || input.trim().isEmpty)) {
          return '${column.name} is required';
        }
        if (input == null || input.trim().isEmpty) return null;
        try {
          final money = Money.parse(input);
          if (money.isNegative && !column.allowNegative) {
            return '${column.name} cannot be negative';
          }
        } on FormatException {
          return 'Enter a valid amount';
        }
        return null;
      },
      onChanged: (input) => onChanged(input.isEmpty ? null : input),
    );
  }
}
