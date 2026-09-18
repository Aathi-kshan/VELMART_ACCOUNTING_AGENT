import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

/// Desktop data grid chrome (design.md §11.3 / §21.4). Callers still
/// supply [DataColumn]/[DataRow]; this wraps them with Velmart density,
/// heading style, and a surface card. Horizontal scroll is allowed on
/// expanded widths only — compact screens should use [AppRecordCard].
class AppDataTable extends StatelessWidget {
  const AppDataTable({
    super.key,
    required this.columns,
    required this.rows,
    this.headingRowHeight = 44,
    this.dataRowMinHeight = 44,
  });

  final List<DataColumn> columns;
  final List<DataRow> rows;
  final double headingRowHeight;
  final double dataRowMinHeight;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Card(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final minWidth = constraints.maxWidth.isFinite
              ? constraints.maxWidth
              : MediaQuery.sizeOf(context).width;
          return SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: ConstrainedBox(
              constraints: BoxConstraints(minWidth: minWidth),
              child: DataTable(
                headingRowHeight: headingRowHeight,
                dataRowMinHeight: dataRowMinHeight,
                dataRowMaxHeight: 56,
                headingRowColor: const WidgetStatePropertyAll(AppColors.surfaceSubtle),
                headingTextStyle: textTheme.labelLarge?.copyWith(
                  color: AppColors.textSecondary,
                ),
                dataTextStyle: textTheme.bodyLarge,
                columnSpacing: AppSpacing.xl,
                horizontalMargin: AppSpacing.md,
                showCheckboxColumn: false,
                columns: columns,
                rows: rows,
              ),
            ),
          );
        },
      ),
    );
  }
}
