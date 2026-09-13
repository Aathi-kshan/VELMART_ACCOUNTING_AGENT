import 'package:flutter/material.dart';

import '../../../domain/column.dart';

/// SELECT and MULTI_SELECT (plan sections 10.2, 11.4). A SELECT can be
/// marked `is_protected` — locked here for everyone, owner included (P4):
/// the record detail screen's dedicated "Change status" action, calling
/// `PATCH /records/{id}/protected-field`, is the only way to change it.
class SelectFieldRenderer extends StatelessWidget {
  const SelectFieldRenderer({
    super.key,
    required this.column,
    required this.value,
    required this.onChanged,
    this.enabled = true,
    this.isProtectedLocked = false,
    this.errorText,
  });

  final PageColumn column;
  final Object? value;
  final ValueChanged<Object?> onChanged;
  final bool enabled;
  final bool isProtectedLocked;
  final String? errorText;

  bool get _isMulti => column.dataType == ColumnType.multiSelect;

  @override
  Widget build(BuildContext context) {
    if (_isMulti) {
      final selected = (value is List ? (value as List).cast<String>() : const <String>[])
          .toSet();
      return InputDecorator(
        decoration: InputDecoration(
          labelText: column.name,
          border: const OutlineInputBorder(),
          errorText: errorText,
          helperText: column.description,
        ),
        child: Wrap(
          spacing: 8,
          runSpacing: 4,
          children: column.options.map((option) {
            return FilterChip(
              label: Text(option),
              selected: selected.contains(option),
              onSelected: enabled
                  ? (isSelected) {
                      final next = {...selected};
                      if (isSelected) {
                        next.add(option);
                      } else {
                        next.remove(option);
                      }
                      onChanged(next.toList());
                    }
                  : null,
            );
          }).toList(),
        ),
      );
    }

    final currentValue = value is String ? value as String : null;
    return DropdownButtonFormField<String>(
      initialValue: (currentValue != null && column.options.contains(currentValue))
          ? currentValue
          : null,
      decoration: InputDecoration(
        labelText: column.name,
        border: const OutlineInputBorder(),
        errorText: errorText,
        helperText: isProtectedLocked
            ? 'Change this from the record detail screen'
            : column.description,
        suffixIcon: isProtectedLocked ? const Icon(Icons.lock_outline) : null,
      ),
      items: column.options
          .map((option) => DropdownMenuItem(value: option, child: Text(option)))
          .toList(),
      onChanged: enabled ? (next) => onChanged(next) : null,
      validator: (input) {
        if (column.isRequired && input == null) {
          return '${column.name} is required';
        }
        return null;
      },
    );
  }
}
