import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../application/pages_providers.dart';
import '../domain/page.dart';
import '../domain/validation_rule.dart';

/// The Owner adds, edits, and archives a page's `page_validations` rules
/// (plan section 11.3, P4 §6) — an ERROR rule blocks a save outright; a
/// WARNING rule lets it through but flags the record for review (see
/// `record_detail_screen.dart`'s "Needs review" chip and `test_review_queue`
/// on the backend for the filtering this feeds).
///
/// A rule's expression uses the same safe grammar as a FORMULA column
/// (`app/core/expressions/parser.py`) — column keys, `+ - * /`, comparisons,
/// and the small function library (`sum`, `round`, `safe_div`, ...). There is
/// no live preview here (out of scope, per the P4 plan: that would need a
/// second, Dart implementation of the evaluator kept in sync with the
/// Python one) — a rule is checked when it's saved, same as a formula.
class ValidationEditorScreen extends ConsumerWidget {
  const ValidationEditorScreen({super.key, required this.pageId});

  final String pageId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final schemaAsync = ref.watch(pageSchemaProvider(pageId));
    return Scaffold(
      appBar: AppBar(title: const Text('Validation rules')),
      body: schemaAsync.when(
        data: (schema) => _ValidationEditorBody(pageId: pageId, schema: schema),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('Could not load this page.\n$error')),
      ),
    );
  }
}

class _ValidationEditorBody extends ConsumerStatefulWidget {
  const _ValidationEditorBody({required this.pageId, required this.schema});

  final String pageId;
  final PageSchema schema;

  @override
  ConsumerState<_ValidationEditorBody> createState() => _ValidationEditorBodyState();
}

class _ValidationEditorBodyState extends ConsumerState<_ValidationEditorBody> {
  bool _isBusy = false;
  String? _error;

  void _reload() => ref.invalidate(pageSchemaProvider(widget.pageId));

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _isBusy = true;
      _error = null;
    });
    try {
      await action();
      _reload();
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  Future<void> _addRule() async {
    final draft = await _showRuleDialog(context);
    if (draft == null) return;
    await _run(
      () => ref
          .read(pageRepositoryProvider)
          .createValidation(
            widget.pageId,
            name: draft.name,
            expression: draft.expression,
            severity: draft.severity,
            message: draft.message,
          ),
    );
  }

  Future<void> _editRule(ValidationRule rule) async {
    final draft = await _showRuleDialog(
      context,
      existing: _RuleDraft(
        name: rule.name,
        expression: rule.expression,
        severity: rule.severity,
        message: rule.message,
      ),
    );
    if (draft == null) return;
    await _run(
      () => ref
          .read(pageRepositoryProvider)
          .updateValidation(
            rule.id,
            name: draft.name,
            expression: draft.expression,
            severity: draft.severity,
            message: draft.message,
          ),
    );
  }

  Future<void> _archiveRule(ValidationRule rule) async {
    await _run(() => ref.read(pageRepositoryProvider).archiveValidation(rule.id));
  }

  @override
  Widget build(BuildContext context) {
    final rules = widget.schema.validations;
    return Column(
      children: [
        if (_error != null)
          MaterialBanner(
            content: Text(_error!),
            actions: [
              TextButton(onPressed: () => setState(() => _error = null), child: const Text('Dismiss')),
            ],
          ),
        if (_isBusy) const LinearProgressIndicator(),
        Expanded(
          child: rules.isEmpty
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: Text(
                      'No validation rules yet. Add one to block bad saves (ERROR) or '
                      'just flag them for review (WARNING).',
                      textAlign: TextAlign.center,
                    ),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(8),
                  itemCount: rules.length,
                  itemBuilder: (context, index) {
                    final rule = rules[index];
                    return Card(
                      child: ListTile(
                        leading: Icon(
                          rule.severity == ValidationSeverity.error
                              ? Icons.block
                              : Icons.warning_amber_outlined,
                          color: rule.severity == ValidationSeverity.error
                              ? Theme.of(context).colorScheme.error
                              : Colors.orange,
                        ),
                        title: Text(rule.name),
                        subtitle: Text('${rule.expression}\n${rule.message}'),
                        isThreeLine: true,
                        onTap: () => _editRule(rule),
                        trailing: IconButton(
                          icon: const Icon(Icons.archive_outlined),
                          tooltip: 'Archive rule',
                          onPressed: () => _archiveRule(rule),
                        ),
                      ),
                    );
                  },
                ),
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: FilledButton.icon(
            onPressed: _addRule,
            icon: const Icon(Icons.add),
            label: const Text('Add rule'),
          ),
        ),
      ],
    );
  }
}

class _RuleDraft {
  _RuleDraft({
    required this.name,
    required this.expression,
    required this.severity,
    required this.message,
  });

  final String name;
  final String expression;
  final ValidationSeverity severity;
  final String message;
}

Future<_RuleDraft?> _showRuleDialog(BuildContext context, {_RuleDraft? existing}) {
  return showDialog<_RuleDraft>(
    context: context,
    builder: (context) => _RuleDialog(existing: existing),
  );
}

class _RuleDialog extends StatefulWidget {
  const _RuleDialog({this.existing});

  final _RuleDraft? existing;

  @override
  State<_RuleDialog> createState() => _RuleDialogState();
}

class _RuleDialogState extends State<_RuleDialog> {
  final _formKey = GlobalKey<FormState>();
  late final _nameController = TextEditingController(text: widget.existing?.name ?? '');
  late final _expressionController = TextEditingController(
    text: widget.existing?.expression ?? '',
  );
  late final _messageController = TextEditingController(text: widget.existing?.message ?? '');
  late ValidationSeverity _severity = widget.existing?.severity ?? ValidationSeverity.error;

  @override
  void dispose() {
    _nameController.dispose();
    _expressionController.dispose();
    _messageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.existing == null ? 'Add validation rule' : 'Edit validation rule'),
      content: SizedBox(
        width: 420,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextFormField(
                  controller: _nameController,
                  decoration: const InputDecoration(labelText: 'Rule name'),
                  validator: (input) =>
                      (input == null || input.trim().isEmpty) ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _expressionController,
                  decoration: const InputDecoration(
                    labelText: 'Expression',
                    helperText:
                        'A column key, arithmetic, and comparisons — e.g. '
                        'abs(total - expected) <= 1',
                  ),
                  minLines: 1,
                  maxLines: 3,
                  validator: (input) =>
                      (input == null || input.trim().isEmpty) ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<ValidationSeverity>(
                  initialValue: _severity,
                  decoration: const InputDecoration(labelText: 'Severity'),
                  items: [
                    for (final severity in ValidationSeverity.values)
                      DropdownMenuItem(value: severity, child: Text(severity.label)),
                  ],
                  onChanged: (next) => setState(() => _severity = next ?? _severity),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _messageController,
                  decoration: const InputDecoration(
                    labelText: 'Message',
                    helperText: 'Shown to whoever tries a save that fails this rule',
                  ),
                  validator: (input) =>
                      (input == null || input.trim().isEmpty) ? 'Required' : null,
                ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            if (!(_formKey.currentState?.validate() ?? false)) return;
            Navigator.of(context).pop(
              _RuleDraft(
                name: _nameController.text.trim(),
                expression: _expressionController.text.trim(),
                severity: _severity,
                message: _messageController.text.trim(),
              ),
            );
          },
          child: const Text('Save'),
        ),
      ],
    );
  }
}
