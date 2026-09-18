import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_radii.dart';
import '../theme/app_spacing.dart';

/// Loading placeholder (token board LOADING). Prefer the shimmer skeleton
/// over a branded splash; [message] is optional helper copy.
class AppLoadingState extends StatelessWidget {
  const AppLoadingState({super.key, this.message, this.skeleton = true});

  final String? message;
  final bool skeleton;

  @override
  Widget build(BuildContext context) {
    if (!skeleton) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(strokeWidth: 2.5),
              ),
              if (message != null) ...[
                const SizedBox(height: AppSpacing.md),
                Text(
                  message!,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ],
          ),
        ),
      );
    }

    return const Padding(
      padding: EdgeInsets.all(AppSpacing.md),
      child: _ShimmerBlock(),
    );
  }
}

class AppSkeletonCard extends StatelessWidget {
  const AppSkeletonCard({super.key});

  @override
  Widget build(BuildContext context) {
    return const _ShimmerBlock();
  }
}

class _ShimmerBlock extends StatefulWidget {
  const _ShimmerBlock();

  @override
  State<_ShimmerBlock> createState() => _ShimmerBlockState();
}

class _ShimmerBlockState extends State<_ShimmerBlock>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1600),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween(begin: 0.55, end: 1.0).animate(
        CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _bar(widthFactor: 0.55, height: 14),
          const SizedBox(height: AppSpacing.smMd),
          _bar(widthFactor: 0.75, height: 24),
          const SizedBox(height: AppSpacing.sm),
          _bar(widthFactor: 0.4, height: 10),
        ],
      ),
    );
  }

  Widget _bar({required double widthFactor, required double height}) {
    return FractionallySizedBox(
      widthFactor: widthFactor,
      child: Container(
        height: height,
        decoration: const BoxDecoration(
          color: AppColors.surfaceDisabled,
          borderRadius: AppRadii.xsRadius,
        ),
      ),
    );
  }
}
