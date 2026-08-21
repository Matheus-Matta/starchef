class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  final String accessToken;
  final String refreshToken;
  final AuthUser user;

  factory AuthSession.fromJson(Map<String, dynamic> json) => AuthSession(
    accessToken: json['access'] as String,
    refreshToken: json['refresh'] as String,
    user: AuthUser.fromJson(json['user'] as Map<String, dynamic>),
  );

  Map<String, dynamic> toJson() => {
    'access': accessToken,
    'refresh': refreshToken,
    'user': user.toJson(),
  };
}

class AuthUser {
  const AuthUser({
    required this.id,
    required this.username,
    required this.name,
    this.accountId,
    this.branchName,
    this.restaurantName,
    this.restaurantId,
    this.profileType,
    this.isSuperuser = false,
    this.permissions = const [],
  });

  final String id;
  final String username;
  final String name;
  final String? accountId;
  final String? branchName;
  final String? restaurantName;
  final String? restaurantId;
  final String? profileType;
  final bool isSuperuser;
  final List<String> permissions;

  bool get canManageDevices =>
      isSuperuser ||
      profileType == 'admin' ||
      profileType == 'owner' ||
      permissions.contains('*') ||
      permissions.contains('devices.manage');

  bool get canManageTopology =>
      isSuperuser ||
      profileType == 'admin' ||
      profileType == 'owner' ||
      permissions.contains('*') ||
      permissions.contains('topology.manage');

  bool get canViewOrders =>
      isSuperuser ||
      profileType == 'admin' ||
      profileType == 'owner' ||
      permissions.contains('*') ||
      permissions.contains('orders.view') ||
      permissions.contains('orders.manage') ||
      permissions.contains('payments.manage');

  bool get canManageOrders =>
      isSuperuser ||
      profileType == 'admin' ||
      profileType == 'owner' ||
      permissions.contains('*') ||
      permissions.contains('orders.manage');

  bool get canProcessPayments =>
      isSuperuser ||
      profileType == 'admin' ||
      profileType == 'owner' ||
      permissions.contains('*') ||
      permissions.contains('payments.manage');

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
    id: json['id'] as String,
    username: json['username'] as String,
    name: (json['name'] as String?)?.trim() ?? '',
    accountId: json['account_id'] as String?,
    branchName: json['branch_name'] as String?,
    restaurantName: json['restaurant_name'] as String?,
    restaurantId: json['restaurant_id'] as String?,
    profileType: json['profile_type'] as String?,
    isSuperuser: json['is_superuser'] as bool? ?? false,
    permissions: (json['permissions'] as List? ?? const [])
        .map((item) => '$item')
        .toList(),
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'username': username,
    'name': name,
    'account_id': accountId,
    'branch_name': branchName,
    'restaurant_name': restaurantName,
    'restaurant_id': restaurantId,
    'profile_type': profileType,
    'is_superuser': isSuperuser,
    'permissions': permissions,
  };
}
