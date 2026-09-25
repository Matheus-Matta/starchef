class WaiterSession {
  const WaiterSession({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  final String accessToken;
  final String refreshToken;
  final WaiterUser user;

  WaiterSession withTokens(String access, String refresh) =>
      WaiterSession(accessToken: access, refreshToken: refresh, user: user);

  Map<String, dynamic> toJson() => {
    'access': accessToken,
    'refresh': refreshToken,
    'user': user.toJson(),
  };

  static WaiterSession fromJson(Map<String, dynamic> json) => WaiterSession(
    accessToken: '${json['access'] ?? ''}',
    refreshToken: '${json['refresh'] ?? ''}',
    user: WaiterUser.fromJson(
      Map<String, dynamic>.from(json['user'] as Map? ?? const {}),
    ),
  );
}

class WaiterUser {
  const WaiterUser({
    required this.id,
    required this.username,
    required this.name,
    required this.accountId,
    required this.restaurantId,
    this.restaurantName = '',
    this.profileType = '',
    this.permissions = const [],
    this.requireOperatorCode = false,
  });

  final String id;
  final String username;
  final String name;
  final String accountId;
  final String restaurantId;
  final String restaurantName;
  final String profileType;
  final List<String> permissions;

  /// O restaurante pede o código de quem lançou antes de criar pedido ou item?
  ///
  /// Vem com a SESSÃO, e não de uma consulta ao cadastro do restaurante: o app
  /// precisa da resposta antes do primeiro lançamento, e perguntar ao
  /// `/restaurants/` exigiria dar ao garçom leitura do cadastro inteiro só para
  /// descobrir se deve pedir um número.
  ///
  /// Muda no próximo login ou na revalidação da sessão — ligar a opção no meio
  /// do serviço não interrompe quem está atendendo.
  final bool requireOperatorCode;

  String get displayName => name.trim().isEmpty ? username : name.trim();
  bool get canReceivePayment =>
      permissions.contains('*') ||
      permissions.contains('payments.manage') ||
      permissions.contains('cash.manage');

  Map<String, dynamic> toJson() => {
    'id': id,
    'username': username,
    'name': name,
    'account_id': accountId,
    'restaurant_id': restaurantId,
    'restaurant_name': restaurantName,
    'profile_type': profileType,
    'permissions': permissions,
    'require_operator_code': requireOperatorCode,
  };

  static WaiterUser fromJson(Map<String, dynamic> json) => WaiterUser(
    id: '${json['id'] ?? ''}',
    username: '${json['username'] ?? ''}',
    name: '${json['name'] ?? ''}',
    accountId: '${json['account_id'] ?? ''}',
    restaurantId: '${json['restaurant_id'] ?? ''}',
    restaurantName: '${json['restaurant_name'] ?? ''}',
    profileType: '${json['profile_type'] ?? ''}',
    permissions: (json['permissions'] as List? ?? const [])
        .map((item) => '$item')
        .toList(),
    requireOperatorCode: json['require_operator_code'] == true,
  );
}
