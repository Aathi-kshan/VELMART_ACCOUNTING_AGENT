/// A `page_validations` rule — an Owner-authored ERROR/WARNING check over a
/// page's own columns and its FORMULA results (plan section 11.3, P4 §6).
///
/// Mirrors `ValidationRuleOut` in `app/schemas/validation.py`.
library;

class ValidationRule {
  const ValidationRule({
    required this.id,
    required this.pageId,
    required this.name,
    required this.expression,
    required this.severity,
    required this.message,
    required this.isActive,
  });

  factory ValidationRule.fromJson(Map<String, dynamic> json) {
    return ValidationRule(
      id: json['id'] as String,
      pageId: json['page_id'] as String,
      name: json['name'] as String,
      expression: json['expression'] as String,
      severity: ValidationSeverity.fromWire(json['severity'] as String),
      message: json['message'] as String,
      isActive: json['is_active'] as bool,
    );
  }

  final String id;
  final String pageId;
  final String name;
  final String expression;
  final ValidationSeverity severity;
  final String message;
  final bool isActive;
}

/// `ERROR` blocks the save outright; `WARNING` lets it through but flags the
/// record `needs_review` (plan section 11.3, P4 §6/§9).
enum ValidationSeverity {
  error,
  warning;

  static ValidationSeverity fromWire(String value) => switch (value) {
    'ERROR' => ValidationSeverity.error,
    'WARNING' => ValidationSeverity.warning,
    _ => throw ArgumentError('Unknown validation severity: $value'),
  };

  String get wire => this == ValidationSeverity.error ? 'ERROR' : 'WARNING';

  String get label =>
      this == ValidationSeverity.error ? 'Error — blocks the save' : 'Warning — flags for review';
}
