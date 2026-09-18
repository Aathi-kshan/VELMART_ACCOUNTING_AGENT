import 'package:flutter/material.dart';

import '../../../../../core/theme/app_colors.dart';
import '../../../domain/column.dart';

/// FORMULA (plan section 11.1) — computed server-side, never stored, never
/// writable. P3 has no evaluator yet (that's P4), so the server omits the
/// value from `data` entirely; this renders a placeholder rather than blank
/// space, so the Owner knows the column exists and why it looks empty.
class FormulaFieldRenderer extends StatelessWidget {
  const FormulaFieldRenderer({super.key, required this.column, required this.value});

  final PageColumn column;
  final Object? value;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      initialValue: value?.toString() ?? 'Computed automatically',
      enabled: false,
      decoration: InputDecoration(
        labelText: column.name,
        filled: true,
        fillColor: AppColors.surfaceSubtle,
        helperText: column.description ?? 'This value is calculated, not entered',
        prefixIcon: const Icon(Icons.functions),
      ),
    );
  }
}
