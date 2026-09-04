import 'dart:async';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../logging/app_logger.dart';
import 'app_paths.dart';

/// Contrato mínimo compartilhado pelos armazenamentos de sessão, senha de
/// caixa e pareamento da rede local.
abstract interface class SecureValueStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class FlutterSecureValueStore implements SecureValueStore {
  FlutterSecureValueStore([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

/// Arquivo de contingência do Linux, isolado pelo usuário do sistema.
///
/// `flutter_secure_storage` depende de um Secret Service desbloqueado. Em
/// instalações Ubuntu minimalistas, autostart e algumas sessões sem GNOME
/// Keyring, o plugin pode lançar erro ou simplesmente devolver `null` depois
/// de reiniciar. O resultado anterior era perder o login e gerar outra chave
/// de pareamento a cada abertura.
///
/// Cada valor fica num arquivo separado, com nome derivado da chave, diretório
/// `0700` e arquivo `0600`. O conteúdo continua sendo credencial sensível: esta
/// proteção depende de o PDV sempre rodar com o mesmo usuário normal, nunca
/// com `sudo`, e não substitui criptografia de disco quando esse risco existir.
class OwnerProtectedFileValueStore implements SecureValueStore {
  OwnerProtectedFileValueStore({Directory? directory, bool? enforceModes})
    : _directory =
          directory ??
          Directory(
            '${AppPaths.dataDirectory().path}${Platform.pathSeparator}secure',
          ),
      _enforceModes = enforceModes ?? (Platform.isLinux || Platform.isMacOS);

  final Directory _directory;
  final bool _enforceModes;
  Future<void> _writeTail = Future.value();

  String _fileName(String key) => '${sha256.convert(key.codeUnits)}.secret';

  File _file(String key) =>
      File('${_directory.path}${Platform.pathSeparator}${_fileName(key)}');

  Future<void> _prepareDirectory() async {
    await _directory.create(recursive: true);
    await _chmod(_directory.path, '700');
  }

  /// Restringe as permissões, sem impedir a gravação quando não consegue.
  ///
  /// Antes uma falha aqui abortava a escrita inteira. Em Ubuntu isso acontece
  /// mais do que parece: `chmod` ausente num empacotamento restrito, volume
  /// montado que não aceita mudança de modo, `$HOME` em exFAT de um pendrive.
  /// Com o keyring também indisponível — o caso comum num autostart sem
  /// sessão gráfica —, o resultado era **perder o login ao fechar o PDV**.
  ///
  /// Um arquivo com a permissão padrão do usuário é um risco menor do que o
  /// operador não conseguir entrar no caixa amanhã de manhã. A falha vira
  /// registro e [permissionsUnenforced], para que o alerta de inicialização
  /// possa mostrá-la.
  Future<void> _chmod(String path, String mode) async {
    if (!_enforceModes) return;
    try {
      final result = await Process.run('chmod', [mode, path]);
      if (result.exitCode == 0) return;
      _reportUnprotected(path, 'chmod devolveu ${result.exitCode}');
    } on ProcessException catch (error) {
      _reportUnprotected(path, error.message);
    }
  }

  /// O armazenamento existe, mas não foi possível restringir as permissões.
  bool get permissionsUnenforced => _permissionsUnenforced;
  bool _permissionsUnenforced = false;
  bool _reported = false;

  void _reportUnprotected(String path, String cause) {
    _permissionsUnenforced = true;
    if (_reported) return;
    _reported = true;
    AppLogger.instance.error(
      'secure_fallback_sem_permissao_restrita',
      data: {'path': path, 'causa': cause},
    );
  }

  @override
  Future<String?> read(String key) async {
    await _prepareDirectory();
    final file = _file(key);
    if (!await file.exists()) return null;
    await _chmod(file.path, '600');
    return file.readAsString();
  }

  @override
  Future<void> write(String key, String value) {
    // Uma instância pode receber refresh, sincronização do hash e mudança de
    // pareamento quase ao mesmo tempo. Encadear evita que dois temporários do
    // mesmo processo disputem o destino.
    final operation = _writeTail.catchError((_) {}).then((_) async {
      await _prepareDirectory();
      final file = _file(key);
      final temporary = File(
        '${file.path}.${pid}_${DateTime.now().microsecondsSinceEpoch}.tmp',
      );
      try {
        await temporary.writeAsString(value, flush: true);
        await _chmod(temporary.path, '600');
        try {
          await temporary.rename(file.path);
        } on FileSystemException {
          // Windows não substitui sempre o destino no rename. O fallback é
          // usado em produção somente no Linux; este ramo mantém os testes e
          // ferramentas locais portáveis.
          if (await file.exists()) await file.delete();
          await temporary.rename(file.path);
        }
        await _chmod(file.path, '600');
      } finally {
        if (await temporary.exists()) await temporary.delete();
      }
    });
    _writeTail = operation;
    return operation;
  }

  @override
  Future<void> delete(String key) {
    final operation = _writeTail.catchError((_) {}).then((_) async {
      await _prepareDirectory();
      final file = _file(key);
      if (await file.exists()) await file.delete();
    });
    _writeTail = operation;
    return operation;
  }
}

/// Cofre resiliente: usa o armazenamento nativo e, no Linux, espelha os
/// valores numa área persistente acessível somente ao usuário do PDV.
///
/// O arquivo é lido primeiro quando existe. Isso é importante porque um
/// keyring pode voltar a ficar disponível com um valor antigo depois de uma
/// abertura em que estava bloqueado; nesse caso ele não pode fazer a chave do
/// Caixa Principal voltar no tempo e desconectar todos os clientes de novo.
class DurableSecureStore implements SecureValueStore {
  DurableSecureStore({
    SecureValueStore? primary,
    SecureValueStore? fallback,
    bool? enablePlatformFallback,
    List<SecureValueStore> extraFallbacks = const [],
  }) : _primary = primary ?? FlutterSecureValueStore(),
       _fallbacks = [
         ?(fallback ??
             ((enablePlatformFallback ?? Platform.isLinux)
                 ? OwnerProtectedFileValueStore()
                 : null)),
         ...extraFallbacks,
       ];

  final SecureValueStore _primary;

  /// Camadas duráveis, na ordem em que são consultadas.
  ///
  /// Mais de uma porque cada uma falha por um motivo diferente: o arquivo
  /// depende de `chmod` e do volume onde fica o `$HOME`; o banco depende de o
  /// SQLite ter aberto. Perder o login por causa de uma delas deixaria o
  /// operador sem entrar no caixa no dia seguinte.
  final List<SecureValueStore> _fallbacks;

  @override
  Future<String?> read(String key) async {
    for (final fallback in _fallbacks) {
      try {
        final local = await fallback.read(key);
        if (local != null) {
          await _tryHealPrimary(key, local);
          return local;
        }
      } catch (error, stackTrace) {
        AppLogger.instance.error(
          'secure_fallback_read_failed',
          cause: error,
          stackTrace: stackTrace,
        );
      }
    }

    try {
      final native = await _primary.read(key);
      if (native != null) {
        // Migra instalações existentes sem exigir novo login: a primeira
        // leitura bem-sucedida do keyring cria as cópias duráveis.
        for (final fallback in _fallbacks) {
          try {
            await fallback.write(key, native);
          } catch (error, stackTrace) {
            // O cofre nativo ainda é uma fonte válida. Uma camada que recusa
            // deve produzir o alerta do boot, mas não pode esconder uma sessão
            // que o keyring conseguiu devolver.
            AppLogger.instance.error(
              'secure_fallback_migration_failed',
              cause: error,
              stackTrace: stackTrace,
            );
          }
        }
      }
      return native;
    } catch (error, stackTrace) {
      AppLogger.instance.error(
        'secure_native_read_failed',
        cause: error,
        stackTrace: stackTrace,
      );
      return null;
    }
  }

  @override
  Future<void> write(String key, String value) async {
    // Persiste primeiro onde não depende do keyring. Mesmo que o plugin
    // nativo trave, o login desta abertura não será perdido na próxima.
    var durableWrites = 0;
    Object? lastFallbackError;
    for (final fallback in _fallbacks) {
      try {
        await fallback.write(key, value);
        durableWrites++;
      } catch (error, stackTrace) {
        lastFallbackError = error;
        AppLogger.instance.error(
          'secure_fallback_write_failed',
          cause: error,
          stackTrace: stackTrace,
        );
      }
    }

    var nativeWritten = false;
    try {
      await _primary.write(key, value);
      nativeWritten = true;
    } catch (error, stackTrace) {
      AppLogger.instance.warning(
        'secure_native_write_failed_using_linux_fallback',
        data: {'cause': '$error', 'stack': '$stackTrace'},
      );
    }

    // Uma camada que gravou já garante o próximo boot. Só quando NENHUMA
    // aceitou é que o chamador precisa saber: aí o login realmente não
    // sobreviveria a fechar o PDV.
    if (durableWrites > 0 || nativeWritten) return;
    throw lastFallbackError ??
        StateError('Nenhum armazenamento seguro aceitou gravar "$key".');
  }

  @override
  Future<void> delete(String key) async {
    // Apagar é tentado em TODAS as camadas: uma cópia esquecida faria a sessão
    // do operador anterior voltar na próxima leitura.
    Object? lastError;
    var removed = 0;
    for (final fallback in _fallbacks) {
      try {
        await fallback.delete(key);
        removed++;
      } catch (error, stackTrace) {
        lastError = error;
        AppLogger.instance.error(
          'secure_fallback_delete_failed',
          cause: error,
          stackTrace: stackTrace,
        );
      }
    }

    try {
      await _primary.delete(key);
      removed++;
    } catch (error, stackTrace) {
      lastError = error;
      AppLogger.instance.warning(
        'secure_native_delete_failed_using_linux_fallback',
        data: {'cause': '$error', 'stack': '$stackTrace'},
      );
    }

    // Uma camada indisponível nunca guardou nada — falhar o logout por causa
    // dela deixaria o operador preso na sessão anterior. Só quando NENHUMA
    // aceitou é que o chamador precisa saber.
    if (removed == 0 && lastError != null) throw lastError;
  }

  Future<void> _tryHealPrimary(String key, String value) async {
    try {
      await _primary.write(key, value);
    } catch (error) {
      AppLogger.instance.warning(
        'secure_native_unavailable_using_linux_fallback',
        data: {'cause': '$error'},
      );
    }
  }
}
