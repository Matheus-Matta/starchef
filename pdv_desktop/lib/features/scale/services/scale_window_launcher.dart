import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import '../../../core/storage/app_paths.dart';
import '../../auth/domain/auth_session.dart';

/// Opens each quick-scale workstation as an independent desktop process.
///
/// A process-per-window keeps focus, lifecycle and crashes isolated and allows
/// any number of workstations. Authentication remains in the OS secure store;
/// no access token is exposed through command-line arguments.
abstract final class ScaleWindowLauncher {
  static const modeArgument = '--scale-workstation';
  static const _handoffArgumentPrefix = '--session-handoff=';
  static const _handoffDirectoryName = 'scale-session-handoffs';
  static const _handoffLifetime = Duration(minutes: 1);

  static Future<bool> open({
    String? restaurantId,
    required AuthSession session,
  }) async {
    if (!Platform.isWindows && !Platform.isLinux && !Platform.isMacOS) {
      return false;
    }
    final executable = Platform.resolvedExecutable;
    if (executable.trim().isEmpty) return false;
    String? handoffName;
    if (Platform.isLinux) {
      try {
        handoffName = await prepareSessionHandoff(session);
      } catch (_) {
        return false;
      }
    }
    final arguments = <String>[
      modeArgument,
      if (restaurantId != null && restaurantId.trim().isNotEmpty)
        '--restaurant=${restaurantId.trim()}',
      if (handoffName != null) '$_handoffArgumentPrefix$handoffName',
    ];
    try {
      await Process.start(
        executable,
        arguments,
        mode: ProcessStartMode.detached,
        runInShell: false,
      );
      if (handoffName != null) {
        unawaited(
          Future<void>.delayed(
            _handoffLifetime,
            () => _deleteHandoff(handoffName!),
          ),
        );
      }
      return true;
    } on ProcessException {
      if (handoffName != null) await _deleteHandoff(handoffName);
      return false;
    }
  }

  /// Entrega a sessão para o processo filho sem expor tokens em `ps` ou em
  /// `/proc/<pid>/cmdline`. O argumento contém apenas um nome aleatório; o
  /// conteúdo fica num arquivo 0600, consumido e removido durante o boot.
  static Future<String> prepareSessionHandoff(AuthSession session) async {
    final directory = _handoffDirectory();
    await directory.create(recursive: true);
    if (Platform.isLinux && !await _chmod('700', directory.path)) {
      throw const FileSystemException(
        'Não foi possível proteger o diretório de transferência da sessão.',
      );
    }
    await _clearExpiredHandoffs(directory);

    final name = _randomHandoffName();
    final file = File('${directory.path}${Platform.pathSeparator}$name');
    await file.create(exclusive: true);
    try {
      if (Platform.isLinux && !await _chmod('600', file.path)) {
        throw const FileSystemException(
          'Não foi possível proteger a transferência da sessão.',
        );
      }
      await file.writeAsString(jsonEncode(session.toJson()), flush: true);
      return name;
    } catch (_) {
      await _deleteFile(file);
      rethrow;
    }
  }

  /// Lê uma transferência válida e a apaga mesmo quando o conteúdo estiver
  /// corrompido. Nomes com caminho são recusados para que um argumento externo
  /// nunca consiga fazer o aplicativo ler ou excluir outro arquivo.
  static Future<AuthSession?> takeSession(List<String> arguments) async {
    final name = _handoffNameFrom(arguments);
    if (name == null) return null;
    final file = File(
      '${_handoffDirectory().path}${Platform.pathSeparator}$name',
    );
    try {
      if (!await file.exists()) return null;
      final age = DateTime.now().difference(await file.lastModified());
      if (age.isNegative || age > _handoffLifetime) return null;
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is! Map) return null;
      return AuthSession.fromJson(Map<String, dynamic>.from(decoded));
    } catch (_) {
      return null;
    } finally {
      await _deleteFile(file);
    }
  }

  static bool isScaleWindow(List<String> arguments) =>
      arguments.contains(modeArgument);

  static String? restaurantFrom(List<String> arguments) {
    const prefix = '--restaurant=';
    for (final argument in arguments) {
      if (argument.startsWith(prefix)) {
        final value = argument.substring(prefix.length).trim();
        if (value.isNotEmpty) return value;
      }
    }
    return null;
  }

  static Directory _handoffDirectory() => Directory(
    '${AppPaths.dataDirectory().path}'
    '${Platform.pathSeparator}$_handoffDirectoryName',
  );

  static String? _handoffNameFrom(List<String> arguments) {
    for (final argument in arguments) {
      if (!argument.startsWith(_handoffArgumentPrefix)) continue;
      final name = argument.substring(_handoffArgumentPrefix.length).trim();
      if (RegExp(r'^session-[a-f0-9]{32}\.json$').hasMatch(name)) return name;
      return null;
    }
    return null;
  }

  static String _randomHandoffName() {
    final random = Random.secure();
    final token = List<int>.generate(
      16,
      (_) => random.nextInt(256),
    ).map((value) => value.toRadixString(16).padLeft(2, '0')).join();
    return 'session-$token.json';
  }

  static Future<bool> _chmod(String mode, String path) async {
    try {
      final result = await Process.run('chmod', [mode, path]);
      return result.exitCode == 0;
    } catch (_) {
      return false;
    }
  }

  static Future<void> _clearExpiredHandoffs(Directory directory) async {
    try {
      await for (final entity in directory.list(followLinks: false)) {
        if (entity is! File ||
            !RegExp(
              r'[\\/]session-[a-f0-9]{32}\.json$',
            ).hasMatch(entity.path)) {
          continue;
        }
        final age = DateTime.now().difference(await entity.lastModified());
        if (!age.isNegative && age > _handoffLifetime) {
          await _deleteFile(entity);
        }
      }
    } catch (_) {}
  }

  static Future<void> _deleteHandoff(String name) => _deleteFile(
    File('${_handoffDirectory().path}${Platform.pathSeparator}$name'),
  );

  static Future<void> _deleteFile(File file) async {
    try {
      if (await file.exists()) await file.delete();
    } catch (_) {}
  }
}
