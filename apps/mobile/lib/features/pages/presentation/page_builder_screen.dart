import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_exception.dart';
import '../application/pages_providers.dart';
import '../domain/page.dart';
import 'widgets/column_draft_dialog.dart';

/// The Owner builds a table (plan sections 3.16, 10.1) — a name, an optional
/// description, and however many columns they want, then `POST /pages` in
/// one call. No migration, no deploy: the page exists the moment this
/// screen submits.
class PageBuilderScreen extends ConsumerStatefulWidget {
  const PageBuilderScreen({super.key});

  @override
  ConsumerState<PageBuilderScreen> createState() => _PageBuilderScreenState();
}

class _PageBuilderScreenState extends ConsumerState<PageBuilderScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _descriptionController = TextEditingController();
  PageKind _kind = PageKind.register;
  final List<ColumnDraft> _columns = [];
  bool _isSubmitting = false;
  String? _error;

  Future<void> _addColumn() async {
    final draft = await showColumnDraftDialog(context);
    if (draft != null) setState(() => _columns.add(draft));
  }

  Future<void> _editColumn(int index) async {
    final draft = await showColumnDraftDialog(context, existing: _columns[index]);
    if (draft != null) setState(() => _columns[index] = draft);
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (_columns.isEmpty) {
      setState(() => _error = 'Add at least one column before creating the page.');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _error = null;
    });

    try {
      await ref
          .read(pageRepositoryProvider)
          .createPage(
            name: _nameController.text.trim(),
            kind: _kind,
            description: _descriptionController.text.trim().isEmpty
                ? null
                : _descriptionController.text.trim(),
            columns: _columns.map((c) => c.toDefinition()).toList(),
          );
      ref.invalidate(pagesProvider);
      if (mounted) context.pop();
    } on ApiException catch (e) {
      // 409 RESERVED_PAGE_KEY / 409 (name collision) / the projection-slot
      // 409 all carry a clear `detail` sentence already (plan section 10.3,
      // docs/API.md section 1.7) — shown as-is rather than re-worded.
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New page')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null) ...[
              Card(
                color: Theme.of(context).colorScheme.errorContainer,
                child: Padding(padding: const EdgeInsets.all(12), child: Text(_error!)),
              ),
              const SizedBox(height: 16),
            ],
            TextFormField(
              controller: _nameController,
              decoration: const InputDecoration(
                labelText: 'Page name',
                border: OutlineInputBorder(),
                helperText: 'e.g. "Fuel Receipts" — becomes the table everyone sees',
              ),
              validator: (input) =>
                  (input == null || input.trim().isEmpty) ? 'A name is required' : null,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _descriptionController,
              decoration: const InputDecoration(
                labelText: 'Description (optional)',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<PageKind>(
              initialValue: _kind,
              decoration: const InputDecoration(labelText: 'Kind', border: OutlineInputBorder()),
              items: [
                for (final kind in PageKind.values)
                  DropdownMenuItem(value: kind, child: Text(kind.label)),
              ],
              onChanged: (next) => setState(() => _kind = next ?? _kind),
            ),
            const SizedBox(height: 24),
            Row(
              children: [
                Text('Columns', style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                TextButton.icon(
                  onPressed: _addColumn,
                  icon: const Icon(Icons.add),
                  label: const Text('Add column'),
                ),
              ],
            ),
            if (_columns.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Text('No columns yet — every table needs at least one.'),
              ),
            for (var i = 0; i < _columns.length; i++)
              Card(
                child: ListTile(
                  title: Text(_columns[i].name),
                  subtitle: Text(_columns[i].dataType.label),
                  onTap: () => _editColumn(i),
                  trailing: IconButton(
                    icon: const Icon(Icons.delete_outline),
                    onPressed: () => setState(() => _columns.removeAt(i)),
                  ),
                ),
              ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _isSubmitting ? null : _submit,
              child: _isSubmitting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Create page'),
            ),
          ],
        ),
      ),
    );
  }
}
