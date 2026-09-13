import 'package:flutter/material.dart';

import '../../../../auth/domain/user.dart';
import '../../../domain/column.dart';
import 'attachment_field_renderer.dart';
import 'boolean_field_renderer.dart';
import 'currency_field_renderer.dart';
import 'date_field_renderer.dart';
import 'formula_field_renderer.dart';
import 'number_field_renderer.dart';
import 'record_ref_field_renderer.dart';
import 'select_field_renderer.dart';
import 'text_field_renderer.dart';

/// One dispatcher, 15 column types (plan section 3.12). Every screen that
/// edits or displays a column value — the record form, the column editor's
/// preview, a filter row's value picker — goes through this rather than
/// re-implementing the `ColumnType` switch itself. Get this mapping right
/// once and every table the Owner invents renders correctly with no further
/// work (plan section 22.3).
class FieldRenderer extends StatelessWidget {
  const FieldRenderer({
    super.key,
    required this.column,
    required this.value,
    required this.onChanged,
    required this.role,
    this.enabled = true,
    this.errorText,
  });

  final PageColumn column;
  final Object? value;
  final ValueChanged<Object?> onChanged;
  final UserRole role;
  final bool enabled;
  final String? errorText;

  @override
  Widget build(BuildContext context) {
    // Locked for *everyone*, owner included (a P4 fix) — no one changes a
    // protected value through this generic form any more, only through the
    // dedicated `PATCH /records/{id}/protected-field` action on the record
    // detail screen. `role` still decides whether that action itself is
    // offered there (`canSetProtectedField`), just not whether this field
    // is editable here.
    final isProtectedLocked = column.isProtected;
    final effectiveEnabled = enabled && !column.dataType.isReadOnly && !isProtectedLocked;

    switch (column.dataType) {
      case ColumnType.text:
      case ColumnType.longText:
        return TextFieldRenderer(
          column: column,
          value: value as String?,
          onChanged: onChanged,
          enabled: effectiveEnabled,
          errorText: errorText,
        );
      case ColumnType.number:
      case ColumnType.percent:
        return NumberFieldRenderer(
          column: column,
          value: value as String?,
          onChanged: onChanged,
          enabled: effectiveEnabled,
          errorText: errorText,
        );
      case ColumnType.currency:
        return CurrencyFieldRenderer(
          column: column,
          value: value as String?,
          onChanged: onChanged,
          enabled: effectiveEnabled,
          errorText: errorText,
        );
      case ColumnType.date:
      case ColumnType.datetime:
        return DateFieldRenderer(
          column: column,
          value: value as String?,
          onChanged: onChanged,
          enabled: effectiveEnabled,
          errorText: errorText,
        );
      case ColumnType.boolean:
        return BooleanFieldRenderer(
          column: column,
          value: value as bool?,
          onChanged: onChanged,
          enabled: effectiveEnabled,
        );
      case ColumnType.select:
        return SelectFieldRenderer(
          column: column,
          value: value,
          onChanged: onChanged,
          enabled: effectiveEnabled,
          isProtectedLocked: isProtectedLocked,
          errorText: errorText,
        );
      case ColumnType.multiSelect:
        return SelectFieldRenderer(
          column: column,
          value: value,
          onChanged: onChanged,
          enabled: effectiveEnabled,
          errorText: errorText,
        );
      case ColumnType.recordRef:
      case ColumnType.storeRef:
      case ColumnType.userRef:
        return RecordRefFieldRenderer(
          column: column,
          value: value as String?,
          onChanged: onChanged,
          enabled: effectiveEnabled,
          errorText: errorText,
        );
      case ColumnType.formula:
        return FormulaFieldRenderer(column: column, value: value);
      case ColumnType.attachment:
        return AttachmentFieldRenderer(column: column, value: value);
    }
  }
}
