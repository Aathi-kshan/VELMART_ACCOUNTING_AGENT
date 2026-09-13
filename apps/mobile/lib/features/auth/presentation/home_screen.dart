import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/permissions/can.dart';
import '../../../core/widgets/empty_state.dart';
import '../../dashboard/application/dashboard_providers.dart';
import '../../dashboard/domain/widget.dart';
import '../../pages/domain/record.dart' show AggregateGroup;
import '../application/auth_controller.dart';
import '../domain/user.dart';

/// The Home tab (plan section 22.4): the Owner-assembled dashboard (plan
/// section 15) — no built-in financial widgets, because there are no
/// built-in financial tables. A brand-new company sees starter suggestions
/// instead of an empty screen; the Owner accepts, edits, or ignores each one
/// (plan section 15.3 — never a hard-coded assumption).
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(authControllerProvider);
    final user = state is AuthAuthenticated ? state.user : null;
    final widgetsAsync = ref.watch(dashboardWidgetsProvider);

    if (user == null) {
      return const Center(child: CircularProgressIndicator());
    }

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(dashboardWidgetsProvider),
      child: widgetsAsync.when(
        data: (widgets) => _body(context, ref, user, widgets),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => ListView(
          children: [
            EmptyState(
              icon: Icons.error_outline,
              message: 'Could not load the dashboard.\n$error',
              actionLabel: 'Retry',
              onAction: () => ref.invalidate(dashboardWidgetsProvider),
            ),
          ],
        ),
      ),
    );
  }

  Widget _body(BuildContext context, WidgetRef ref, User user, List<DashboardWidget> widgets) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(user.fullName, style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 4),
        Chip(label: Text(user.role == UserRole.owner ? 'Owner' : 'Manager')),
        const SizedBox(height: 16),
        Card(
          child: ListTile(
            leading: const Icon(Icons.balance_outlined),
            title: const Text('Reconciliation'),
            subtitle: const Text('Daily Revenue vs Cash Ledger'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => context.pushNamed('reconciliation'),
          ),
        ),
        const SizedBox(height: 16),
        if (widgets.isEmpty)
          _SuggestionsSection(role: user.role)
        else ...[
          for (final widget in widgets) _WidgetCard(widget: widget),
        ],
        if (canConfigureDashboard(user.role)) ...[
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () => context.pushNamed('widgetNew'),
            icon: const Icon(Icons.add),
            label: const Text('Add widget'),
          ),
        ],
      ],
    );
  }
}

class _SuggestionsSection extends ConsumerWidget {
  const _SuggestionsSection({required this.role});

  final UserRole role;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!canConfigureDashboard(role)) {
      return const EmptyState(
        icon: Icons.dashboard_customize_outlined,
        message: 'No widgets have been added to the dashboard yet.',
      );
    }
    final suggestionsAsync = ref.watch(widgetSuggestionsProvider);
    return suggestionsAsync.when(
      data: (suggestions) => suggestions.isEmpty
          ? const EmptyState(
              icon: Icons.dashboard_customize_outlined,
              message: 'Tap "Add widget" to build your first dashboard card.',
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Suggested for you', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                for (final suggestion in suggestions) _SuggestionCard(suggestion: suggestion),
              ],
            ),
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (_, _) => const SizedBox.shrink(),
    );
  }
}

class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({required this.suggestion});

  final WidgetSuggestion suggestion;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.auto_awesome_outlined),
        title: Text(suggestion.title),
        subtitle: Text(suggestion.widgetType.label),
        trailing: TextButton(
          onPressed: () => context.pushNamed(
            'widgetNew',
            extra: suggestion,
          ),
          child: const Text('Add'),
        ),
      ),
    );
  }
}

class _WidgetCard extends ConsumerWidget {
  const _WidgetCard({required this.widget});

  final DashboardWidget widget;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dataAsync = ref.watch(widgetDataProvider(widget.id));
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(widget.title, style: Theme.of(context).textTheme.titleMedium),
                ),
                PopupMenuButton<String>(
                  onSelected: (action) async {
                    if (action == 'delete') {
                      await ref.read(dashboardRepositoryProvider).deleteWidget(widget.id);
                      ref.invalidate(dashboardWidgetsProvider);
                    }
                  },
                  itemBuilder: (context) => const [
                    PopupMenuItem(value: 'delete', child: Text('Remove')),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 8),
            dataAsync.when(
              data: (data) => _content(context, data),
              loading: () => const LinearProgressIndicator(),
              error: (error, _) => Text('$error', style: Theme.of(context).textTheme.bodySmall),
            ),
          ],
        ),
      ),
    );
  }

  Widget _content(BuildContext context, WidgetEvaluation data) {
    switch (data.widgetType) {
      case WidgetType.metric:
        return Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(data.value ?? '0', style: Theme.of(context).textTheme.headlineMedium),
            if (data.comparisonValue != null) ...[
              const SizedBox(width: 8),
              Text(
                'vs ${data.comparisonValue}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        );
      case WidgetType.trend:
        return _TrendChart(points: data.series);
      case WidgetType.breakdown:
        return _BreakdownBars(groups: data.groups);
      case WidgetType.list:
      case WidgetType.reviewQueue:
        return data.records.isEmpty
            ? const Text('Nothing to show.')
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final record in data.records.take(5))
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Text(record.data.values.join(' · ')),
                    ),
                ],
              );
    }
  }
}

class _TrendChart extends StatelessWidget {
  const _TrendChart({required this.points});

  final List<TrendPoint> points;

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) return const Text('No data for this period.');
    final spots = <FlSpot>[
      for (var i = 0; i < points.length; i++)
        FlSpot(i.toDouble(), double.tryParse(points[i].value) ?? 0),
    ];
    return SizedBox(
      height: 160,
      child: LineChart(
        LineChartData(
          titlesData: const FlTitlesData(show: false),
          gridData: const FlGridData(show: false),
          borderData: FlBorderData(show: false),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              barWidth: 2,
              dotData: const FlDotData(show: false),
              color: Theme.of(context).colorScheme.primary,
            ),
          ],
        ),
      ),
    );
  }
}

class _BreakdownBars extends StatelessWidget {
  const _BreakdownBars({required this.groups});

  final List<AggregateGroup> groups;

  @override
  Widget build(BuildContext context) {
    if (groups.isEmpty) return const Text('No data for this period.');
    final values = [for (final g in groups) double.tryParse(g.value) ?? 0];
    final maxValue = values.reduce((a, b) => a > b ? a : b);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < groups.length; i++)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                SizedBox(
                  width: 80,
                  child: Text(groups[i].key, overflow: TextOverflow.ellipsis),
                ),
                Expanded(
                  child: FractionallySizedBox(
                    alignment: Alignment.centerLeft,
                    widthFactor: maxValue == 0 ? 0 : (values[i] / maxValue).clamp(0.02, 1.0),
                    child: Container(height: 12, color: Theme.of(context).colorScheme.primary),
                  ),
                ),
                const SizedBox(width: 8),
                Text(groups[i].value),
              ],
            ),
          ),
      ],
    );
  }
}
