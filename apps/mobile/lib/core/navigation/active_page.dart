import 'package:flutter_riverpod/flutter_riverpod.dart';

/// The page currently (or last) opened in the record list — used by the
/// shell's center **+** so Add record has a real destination.
class ActivePage {
  const ActivePage({this.id, this.name});

  final String? id;
  final String? name;

  bool get hasPage => id != null;
}

final activePageProvider = StateProvider<ActivePage>((ref) => const ActivePage());
