import 'dart:io';

import 'package:archive/archive_io.dart';

import '../storage/app_paths.dart';
import 'pdv_update_service.dart';

class PdvPreparedUpdate {
  const PdvPreparedUpdate({
    required this.version,
    required this.installDirectory,
    required this.stagingDirectory,
    required this.backupDirectory,
    required this.executableName,
    required this.helperScript,
  });

  final String version;
  final Directory installDirectory;
  final Directory stagingDirectory;
  final Directory backupDirectory;
  final String executableName;
  final File helperScript;
}

/// Prepara o bundle novo sem tocar na instalação em uso. A troca é feita por
/// outro processo somente depois que o PDV encerra.
class PdvUpdateInstaller {
  PdvUpdateInstaller({File? executable})
    : executable = executable ?? File(Platform.resolvedExecutable);

  final File executable;

  Future<PdvPreparedUpdate> prepare(
    PdvDownloadedArtifact download,
    String version,
  ) async {
    if (!Platform.isWindows && !Platform.isLinux) {
      throw UnsupportedError('Atualização automática não suportada neste SO');
    }
    if (download.artifact.format.toLowerCase() != 'zip') {
      throw const FormatException(
        'O rollback automático exige o pacote portátil ZIP',
      );
    }

    final installDirectory = executable.absolute.parent;
    _validateInstallDirectory(installDirectory);
    final transaction = '${_safeVersion(version)}-$pid';
    final stagingDirectory = Directory(
      '${installDirectory.path}.starchef-new-$transaction',
    );
    final backupDirectory = Directory(
      '${installDirectory.path}.starchef-backup-$transaction',
    );
    _validateManagedSibling(installDirectory, stagingDirectory);
    _validateManagedSibling(installDirectory, backupDirectory);
    if (await stagingDirectory.exists() || await backupDirectory.exists()) {
      throw const FileSystemException(
        'Diretório de transação já existe; atualização não iniciada',
      );
    }

    try {
      await _extractVerifiedZip(download.file, stagingDirectory);
      final executableName = Platform.isWindows
          ? 'starchef_pdv.exe'
          : 'starchef_pdv';
      final stagedExecutable = File(
        '${stagingDirectory.path}${Platform.pathSeparator}$executableName',
      );
      if (!await stagedExecutable.exists()) {
        throw FormatException(
          'ZIP não contém o executável esperado: $executableName',
        );
      }
      if (Platform.isLinux) {
        final chmod = await Process.run('chmod', [
          '755',
          stagedExecutable.path,
        ]);
        if (chmod.exitCode != 0) {
          throw ProcessException(
            'chmod',
            ['755', stagedExecutable.path],
            '${chmod.stderr}',
            chmod.exitCode,
          );
        }
      }
      await _preserveLocalFile(installDirectory, stagingDirectory, '.env');
      await _preserveLocalFile(
        installDirectory,
        stagingDirectory,
        'liberar_firewall.ps1',
      );

      final helperDirectory = Directory(
        '${AppPaths.dataDirectory().path}${Platform.pathSeparator}updates'
        '${Platform.pathSeparator}$transaction',
      );
      await helperDirectory.create(recursive: true);
      final helperScript = File(
        '${helperDirectory.path}${Platform.pathSeparator}'
        '${Platform.isWindows ? 'apply-update.ps1' : 'apply-update.sh'}',
      );
      await helperScript.writeAsString(
        Platform.isWindows
            ? _windowsHelper(
                installDirectory: installDirectory,
                stagingDirectory: stagingDirectory,
                backupDirectory: backupDirectory,
                executableName: executableName,
                parentPid: pid,
                logFile: File('${helperDirectory.path}\\update.log'),
              )
            : _linuxHelper(
                installDirectory: installDirectory,
                stagingDirectory: stagingDirectory,
                backupDirectory: backupDirectory,
                executableName: executableName,
                parentPid: pid,
                logFile: File('${helperDirectory.path}/update.log'),
              ),
        flush: true,
      );
      return PdvPreparedUpdate(
        version: version,
        installDirectory: installDirectory,
        stagingDirectory: stagingDirectory,
        backupDirectory: backupDirectory,
        executableName: executableName,
        helperScript: helperScript,
      );
    } catch (_) {
      if (await stagingDirectory.exists()) {
        _validateManagedSibling(installDirectory, stagingDirectory);
        await stagingDirectory.delete(recursive: true);
      }
      rethrow;
    }
  }

  Future<void> launch(PdvPreparedUpdate update) async {
    _validateManagedSibling(update.installDirectory, update.stagingDirectory);
    _validateManagedSibling(update.installDirectory, update.backupDirectory);
    if (!await update.helperScript.exists() ||
        !await update.stagingDirectory.exists()) {
      throw const FileSystemException(
        'Atualização preparada não foi encontrada',
      );
    }
    if (Platform.isWindows) {
      await Process.start(
        'powershell.exe',
        [
          '-NoLogo',
          '-NoProfile',
          '-NonInteractive',
          '-ExecutionPolicy',
          'Bypass',
          '-File',
          update.helperScript.path,
        ],
        workingDirectory: update.helperScript.parent.path,
        mode: ProcessStartMode.detached,
      );
      return;
    }
    await Process.start(
      '/bin/sh',
      [update.helperScript.path],
      workingDirectory: update.helperScript.parent.path,
      mode: ProcessStartMode.detached,
    );
  }

  Future<void> _extractVerifiedZip(File zip, Directory output) async {
    final input = InputFileStream(zip.path);
    try {
      final archive = ZipDecoder().decodeStream(input, verify: true);
      var unpackedSize = 0;
      final maximumSize = (await zip.length()) * 50;
      for (final entry in archive) {
        final segments = entry.name.split(RegExp(r'[/\\]+'));
        if (entry.name.startsWith('/') ||
            entry.name.startsWith(r'\') ||
            entry.name.contains(':') ||
            segments.any((part) => part == '..') ||
            entry.isSymbolicLink) {
          throw FormatException('Entrada insegura no ZIP: ${entry.name}');
        }
        unpackedSize += entry.size;
        if (unpackedSize > maximumSize || unpackedSize > 2147483648) {
          throw const FormatException('Conteúdo descompactado excede o limite');
        }
      }
      await extractArchiveToDisk(archive, output.path);
    } finally {
      input.close();
    }
  }

  Future<void> _preserveLocalFile(
    Directory current,
    Directory staging,
    String name,
  ) async {
    final source = File('${current.path}${Platform.pathSeparator}$name');
    final destination = File('${staging.path}${Platform.pathSeparator}$name');
    if (await source.exists() && !await destination.exists()) {
      await source.copy(destination.path);
    }
  }

  void _validateInstallDirectory(Directory directory) {
    final path = directory.absolute.path;
    final parent = directory.absolute.parent.path;
    if (path == parent ||
        path.trim().isEmpty ||
        path.contains(RegExp(r'[\r\n]'))) {
      throw const FileSystemException('Diretório de instalação inseguro');
    }
  }

  void _validateManagedSibling(Directory install, Directory target) {
    final prefix = '${install.absolute.path}.starchef-';
    if (!target.absolute.path.startsWith(prefix) ||
        target.absolute.path.contains(RegExp(r'[\r\n]'))) {
      throw const FileSystemException('Diretório de atualização inseguro');
    }
  }

  String _safeVersion(String value) =>
      value.replaceAll(RegExp(r'[^0-9A-Za-z.-]'), '_');
}

String _ps(String value) => "'${value.replaceAll("'", "''")}'";

String _sh(String value) => "'${value.replaceAll("'", "'\"'\"'")}'";

String _windowsHelper({
  required Directory installDirectory,
  required Directory stagingDirectory,
  required Directory backupDirectory,
  required String executableName,
  required int parentPid,
  required File logFile,
}) {
  final install = _ps(installDirectory.path);
  final staging = _ps(stagingDirectory.path);
  final backup = _ps(backupDirectory.path);
  final executable = _ps('${installDirectory.path}\\$executableName');
  final log = _ps(logFile.path);
  return '''
\$ErrorActionPreference = 'Stop'
\$install = $install
\$staging = $staging
\$backup = $backup
\$executable = $executable
\$log = $log
"Inicio da atualizacao: \$(Get-Date -Format o)" | Out-File -FilePath \$log -Append -Encoding utf8
while (Get-Process -Id $parentPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 250 }
Get-Process -Name 'starchef_pdv' -ErrorAction SilentlyContinue | ForEach-Object {
  try { if (\$_.Path -eq \$executable) { Stop-Process -Id \$_.Id -Force } } catch {}
}
Start-Sleep -Milliseconds 500
\$oldMoved = \$false
\$newProcess = \$null
try {
  Move-Item -LiteralPath \$install -Destination \$backup
  \$oldMoved = \$true
  Move-Item -LiteralPath \$staging -Destination \$install
  \$newProcess = Start-Process -FilePath \$executable -WorkingDirectory \$install -PassThru
  Start-Sleep -Seconds 8
  if (\$newProcess.HasExited) { throw "O PDV novo encerrou durante a validacao" }
  Remove-Item -LiteralPath \$backup -Recurse -Force
  "Atualizacao concluida: \$(Get-Date -Format o)" | Out-File -FilePath \$log -Append -Encoding utf8
  exit 0
} catch {
  "Falha e rollback: \$_" | Out-File -FilePath \$log -Append -Encoding utf8
  if (\$null -ne \$newProcess -and -not \$newProcess.HasExited) {
    Stop-Process -Id \$newProcess.Id -Force -ErrorAction SilentlyContinue
  }
  if (\$oldMoved) {
    if (Test-Path -LiteralPath \$install) { Remove-Item -LiteralPath \$install -Recurse -Force }
    if (Test-Path -LiteralPath \$backup) {
      Move-Item -LiteralPath \$backup -Destination \$install
    }
  }
  if (Test-Path -LiteralPath \$executable) {
    Start-Process -FilePath \$executable -WorkingDirectory \$install
  }
  exit 1
}
''';
}

String _linuxHelper({
  required Directory installDirectory,
  required Directory stagingDirectory,
  required Directory backupDirectory,
  required String executableName,
  required int parentPid,
  required File logFile,
}) {
  final executablePath = '${installDirectory.path}/$executableName';
  return '''#!/bin/sh
set -u
install=${_sh(installDirectory.path)}
staging=${_sh(stagingDirectory.path)}
backup=${_sh(backupDirectory.path)}
executable=${_sh(executablePath)}
log=${_sh(logFile.path)}
exec >>"\$log" 2>&1
echo "Inicio da atualizacao: \$(date -Iseconds)"
while kill -0 $parentPid 2>/dev/null; do sleep 1; done
for proc in /proc/[0-9]*/exe; do
  target=\$(readlink "\$proc" 2>/dev/null || true)
  if [ "\$target" = "\$executable" ]; then
    other_pid=\$(printf '%s' "\$proc" | cut -d/ -f3)
    kill "\$other_pid" 2>/dev/null || true
  fi
done
sleep 1
old_moved=0
new_pid=''
rollback() {
  echo "Falha; executando rollback"
  if [ -n "\$new_pid" ]; then kill "\$new_pid" 2>/dev/null || true; fi
  if [ "\$old_moved" -eq 1 ]; then
    if [ -d "\$install" ]; then rm -rf -- "\$install"; fi
    if [ -d "\$backup" ]; then mv -- "\$backup" "\$install"; fi
  fi
  if [ -x "\$executable" ]; then (cd "\$install" && "\$executable" >/dev/null 2>&1 &); fi
}
if ! mv -- "\$install" "\$backup"; then rollback; exit 1; fi
old_moved=1
if ! mv -- "\$staging" "\$install"; then rollback; exit 1; fi
chmod 755 "\$executable" || { rollback; exit 1; }
(cd "\$install" && "\$executable" >/dev/null 2>&1 & echo \$! > "\$log.pid")
new_pid=\$(cat "\$log.pid")
sleep 8
if ! kill -0 "\$new_pid" 2>/dev/null; then rollback; exit 1; fi
rm -rf -- "\$backup"
echo "Atualizacao concluida: \$(date -Iseconds)"
exit 0
''';
}
