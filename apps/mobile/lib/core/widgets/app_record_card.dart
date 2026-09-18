import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';
import '../theme/app_typography.dart';
import 'amount_text.dart';
import 'app_card.dart';
import 'app_status_chip.dart';

/// Mobile record row (design.md §11.3 / §30): one title, one amount/date
/// line, up to two supporting values, one status, one tap target.
class AppRecordCard extends StatelessWidget {
  const AppRecordCard({
    super.key,
    required this.title,
    this.subtitle,
    this.amount,
    this.supporting = const [],
    this.status,
    this.onTap,
    this.selected = false,
  });

  final String title;
  final String? subtitle;
  final Object? amount;
  final List<String> supporting;
  final Widget? status;
  final VoidCallback? onTap;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final extras = supporting.take(2).toList();

    return AppCard(
      onTap: onTap,
      selected: selected,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  title,
                  style: textTheme.titleMedium,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (amount != null)
                AmountText(amount, style: AppTypography.dataStrong()),
            ],
          ),
          if (subtitle != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(subtitle!, style: textTheme.bodySmall),
          ],
          if (extras.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              extras.join(' · '),
              style: textTheme.bodySmall,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          if (status != null) ...[
            const SizedBox(height: AppSpacing.sm),
            status!,
          ],
        ],
      ),
    );
  }
}

/// Re-export so call sites that already import this file can use the chip.
typedef RecordCardStatus = AppStatusChip;
