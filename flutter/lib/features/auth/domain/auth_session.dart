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
}

class AuthUser {
  const AuthUser({
    required this.id,
    required this.username,
    required this.name,
    this.branchName,
    this.restaurantName,
  });

  final String id;
  final String username;
  final String name;
  final String? branchName;
  final String? restaurantName;

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
    id: json['id'] as String,
    username: json['username'] as String,
    name: (json['name'] as String?)?.trim() ?? '',
    branchName: json['branch_name'] as String?,
    restaurantName: json['restaurant_name'] as String?,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'username': username,
    'name': name,
    'branch_name': branchName,
    'restaurant_name': restaurantName,
  };
}
