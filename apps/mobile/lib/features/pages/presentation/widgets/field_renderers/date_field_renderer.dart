import 'package:flutter/material.dart';

import '../../../../../core/date/business_date.dart';
import '../../../domain/column.dart';

/// DATE and DATETIME (plan section 10.2). Displays and edits on the
/// company's local wall clock; the value handed to `onChanged` is always the
/// wire ISO string the server expects — `toWireDate`/`toWireDateTime` do that
/// conversion, never ad hoc formatting here.
class DateFieldRenderer extends StatelessWidget {
  const DateFieldRenderer({
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

  bool get _isDateTime => column.dataType == ColumnType.datetime;

  String _displayText() {
    if (value == null || value!.isEmpty) return '';
    return _isDateTime ? formatDateTime(value) : formatDate(value);
  }

  Future<void> _pick(BuildContext context) async {
    final now = DateTime.now();
    final initial = (_isDateTime ? parseWireDateTime(value) : parseWireDate(value)) ?? now;

    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(now.year - 10),
      lastDate: DateTime(now.year + 10),
    );
    if (date == null) return;

    if (!_isDateTime) {
      onChanged(toWireDate(date));
      return;
    }

    if (!context.mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(initial),
    );
    if (time == null) return;

    final combined = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    onChanged(toWireDateTime(combined));
  }

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      key: ValueKey('${column.key}-$value'),
      readOnly: true,
      enabled: enabled,
      initialValue: _displayText(),
      decoration: InputDecoration(
        labelText: column.isRequired ? '${column.name} *' : column.name,
        errorText: errorText,
        helperText: column.description,
        suffixIcon: Icon(_isDateTime ? Icons.event : Icons.calendar_today),
      ),
      validator: (_) {
        if (column.isRequired && (value == null || value!.isEmpty)) {
          return '${column.name} is required';
        }
        return null;
      },
      onTap: enabled ? () => _pick(context) : null,
    );
  }
}
