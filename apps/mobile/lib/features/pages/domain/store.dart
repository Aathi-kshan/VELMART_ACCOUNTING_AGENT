/// A store (plan section 4.5) — mirrors `StoreOut` in `app/schemas/store.py`.
///
/// Minimal on purpose: P3 only needs enough to populate a `STORE_REF` picker
/// and, later, a store filter. Store management screens are a later phase.
class Store {
  const Store({
    required this.id,
    required this.companyId,
    required this.code,
    required this.name,
    required this.isActive,
    this.address,
  });

  factory Store.fromJson(Map<String, dynamic> json) => Store(
    id: json['id'] as String,
    companyId: json['company_id'] as String,
    code: json['code'] as String,
    name: json['name'] as String,
    address: json['address'] as String?,
    isActive: json['is_active'] as bool,
  );

  final String id;
  final String companyId;
  final String code;
  final String name;
  final String? address;
  final bool isActive;
}
