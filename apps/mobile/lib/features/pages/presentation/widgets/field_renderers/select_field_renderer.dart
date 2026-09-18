import 'package:flutter/material.dart';

import '../../../../../core/theme/app_colors.dart';
import '../../../../../core/theme/app_spacing.dart';
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
          labelText: column.isRequired ? '${column.name} *' : column.name,
          errorText: errorText,
          helperText: column.description,
        ),
        child: Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.xs,
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
    return FormField<String>(
      initialValue: (currentValue != null && column.options.contains(currentValue))
          ? currentValue
          : null,
      validator: (input) {
        if (column.isRequired && (input == null || input.isEmpty)) {
          return '${column.name} is required';
        }
        return null;
      },
      builder: (state) {
        return InputDecorator(
          decoration: InputDecoration(
            labelText: column.isRequired ? '${column.name} *' : column.name,
            errorText: errorText ?? state.errorText,
            helperText: isProtectedLocked
                ? 'Change this from the record detail screen'
                : column.description,
            suffixIcon: isProtectedLocked ? const Icon(Icons.lock_outline) : null,
          ),
          child: Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.xs,
            children: column.options.map((option) {
              final selected = state.value == option;
              return ChoiceChip(
                label: Text(option),
                selected: selected,
                selectedColor: AppColors.brandPrimarySoft,
                labelStyle: TextStyle(
                  color: selected ? AppColors.brandPrimaryDeep : AppColors.textSecondary,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                ),
                onSelected: enabled
                    ? (isSelected) {
                        if (!isSelected) return;
                        state.didChange(option);
                        onChanged(option);
                      }
                    : null,
              );
            }).toList(),
          ),
        );
      },
    );
  }
}
