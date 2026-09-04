import '../../../core/relay/principal_client.dart';

/// Quem está usando o aparelho agora.
///
/// Só a credencial: o pareamento com o Caixa Principal é do APARELHO e vive
/// separado (ver [SessionStorage]) — trocar o garçom no fim do turno não pode
/// obrigar a configurar o caixa de novo.
class WaiterSession {
  const WaiterSession({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  final String accessToken;
  final String refreshToken;
  final WaiterUser user;

  /// Como este garçom se identifica para o Caixa Principal em cada
  /// requisição assinada.
  RelayIdentity get identity => RelayIdentity(
    accountId: user.accountId,
    actorId: user.id,
    restaurantId: user.restaurantId,
  );

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
  });

  final String id;
  final String username;
  final String name;
  final String accountId;
  final String restaurantId;
  final String restaurantName;
  final String profileType;

  /// Códigos do catálogo de permissões (ver backend `permission_catalog.py`),
  /// vindos do perfil fixo do garçom mais qualquer permissão específica
  /// liberada individualmente para ele (`UserProfile.specific_permissions`).
  final List<String> permissions;

  String get displayName => name.trim().isEmpty ? username : name.trim();

  /// O perfil fixo "Garçom" não inclui `payments.manage`/`cash.manage` — o
  /// aparelho só oferece "Receber" para quem tiver isso liberado à parte.
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
  );
}
