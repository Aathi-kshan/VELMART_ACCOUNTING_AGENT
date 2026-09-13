import '../../pages/domain/record.dart' show AggregateGroup, PageRecord;

/// The five widget types (plan section 15.2, P5). Closed list — a new kind
/// of widget is a new value here *and* a new case in
/// `app/services/dashboard_service.py`'s `evaluate_widget`.
enum WidgetType {
  metric,
  trend,
  breakdown,
  list,
  reviewQueue;

  static WidgetType fromWire(String value) => switch (value) {
    'METRIC' => WidgetType.metric,
    'TREND' => WidgetType.trend,
    'BREAKDOWN' => WidgetType.breakdown,
    'LIST' => WidgetType.list,
    'REVIEW_QUEUE' => WidgetType.reviewQueue,
    _ => throw ArgumentError('Unknown widget type: $value'),
  };

  String get wire => switch (this) {
    WidgetType.metric => 'METRIC',
    WidgetType.trend => 'TREND',
    WidgetType.breakdown => 'BREAKDOWN',
    WidgetType.list => 'LIST',
    WidgetType.reviewQueue => 'REVIEW_QUEUE',
  };

  String get label => switch (this) {
    WidgetType.metric => 'Metric',
    WidgetType.trend => 'Trend',
    WidgetType.breakdown => 'Breakdown',
    WidgetType.list => 'List',
    WidgetType.reviewQueue => 'Review queue',
  };
}

/// Mirrors `WidgetOut` in `app/schemas/dashboard.py`. `config` is
/// type-specific (see the module docstring there) — this client never
/// interprets it beyond passing it through the builder form and back;
/// `app/services/dashboard_service.py` is the only place that gives it
/// meaning.
class DashboardWidget {
  const DashboardWidget({
    required this.id,
    required this.title,
    required this.widgetType,
    required this.pageId,
    required this.config,
    required this.position,
    required this.visibleTo,
    required this.createdAt,
  });

  factory DashboardWidget.fromJson(Map<String, dynamic> json) {
    return DashboardWidget(
      id: json['id'] as String,
      title: json['title'] as String,
      widgetType: WidgetType.fromWire(json['widget_type'] as String),
      pageId: json['page_id'] as String?,
      config: (json['config'] as Map<String, dynamic>?) ?? const {},
      position: json['position'] as int,
      visibleTo: json['visible_to'] as String?,
      createdAt: json['created_at'] as String,
    );
  }

  final String id;
  final String title;
  final WidgetType widgetType;
  final String? pageId;
  final Map<String, dynamic> config;
  final int position;
  //: `null` means visible to every role.
  final String? visibleTo;
  final String createdAt;
}

/// Never persisted until the Owner accepts it (plan section 15.3) —
/// accepting one is just creating a widget with this same shape.
class WidgetSuggestion {
  const WidgetSuggestion({
    required this.title,
    required this.widgetType,
    required this.pageKey,
    required this.config,
  });

  factory WidgetSuggestion.fromJson(Map<String, dynamic> json) {
    return WidgetSuggestion(
      title: json['title'] as String,
      widgetType: WidgetType.fromWire(json['widget_type'] as String),
      pageKey: json['page_key'] as String,
      config: (json['config'] as Map<String, dynamic>?) ?? const {},
    );
  }

  final String title;
  final WidgetType widgetType;
  final String pageKey;
  final Map<String, dynamic> config;
}

class TrendPoint {
  const TrendPoint({required this.bucket, required this.value});

  factory TrendPoint.fromJson(Map<String, dynamic> json) =>
      TrendPoint(bucket: json['bucket'] as String, value: json['value'] as String);

  /// ISO date, the bucket's start.
  final String bucket;

  /// Always a wire-format string (money stays a string all the way through).
  final String value;
}

/// One shape for every widget type (mirrors `WidgetEvaluationResponse`) —
/// only the field(s) matching `widgetType` are populated.
class WidgetEvaluation {
  const WidgetEvaluation({
    required this.widgetType,
    this.value,
    this.comparisonValue,
    this.series = const [],
    this.groups = const [],
    this.records = const [],
    this.recordsHasMore = false,
  });

  factory WidgetEvaluation.fromJson(Map<String, dynamic> json) {
    return WidgetEvaluation(
      widgetType: WidgetType.fromWire(json['widget_type'] as String),
      value: json['value'] as String?,
      comparisonValue: json['comparison_value'] as String?,
      series: (json['series'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(TrendPoint.fromJson)
          .toList(),
      groups: (json['groups'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(AggregateGroup.fromJson)
          .toList(),
      records: (json['records'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(PageRecord.fromJson)
          .toList(),
      recordsHasMore: json['records_has_more'] as bool? ?? false,
    );
  }

  final WidgetType widgetType;
  final String? value;
  final String? comparisonValue;
  final List<TrendPoint> series;
  final List<AggregateGroup> groups;
  final List<PageRecord> records;
  final bool recordsHasMore;
}
