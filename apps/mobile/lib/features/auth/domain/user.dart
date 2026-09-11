/// The authenticated user (mirrors `UserOut` in `app/schemas/auth.py`).
///
/// Exactly two roles (plan section 4.1). `storeIds` is read fresh on every
/// `/me` call rather than trusted from a cache — grants are deliberately not
/// baked into anything long-lived, so a revoked assignment takes effect on
/// the next request.
class User {
  const User({
    required this.id,
    required this.companyId,
    required this.fullName,
    required this.email,
    required this.role,
    required this.storeIds,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as String,
      companyId: json['company_id'] as String,
      fullName: json['full_name'] as String,
      email: json['email'] as String,
      role: UserRole.fromWire(json['role'] as String),
      storeIds: (json['store_ids'] as List<dynamic>).cast<String>(),
    );
  }

  final String id;
  final String companyId;
  final String fullName;
  final String email;
  final UserRole role;
  final List<String> storeIds;

  bool get isOwner => role == UserRole.owner;
}

/// Exactly two roles, no more (plan section 4.1).
enum UserRole {
  owner,
  manager;

  // Enums cannot declare factory constructors in Dart, so this is a static
  // method rather than `factory UserRole.fromWire(...)`.
  static UserRole fromWire(String value) => switch (value) {
    'OWNER' => UserRole.owner,
    'MANAGER' => UserRole.manager,
    _ => throw ArgumentError('Unknown role: $value'),
  };
}
