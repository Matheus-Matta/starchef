import 'dart:io';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/storage/app_paths.dart';
import 'package:starchef_pdv/core/update/pdv_update_installer.dart';
import 'package:starchef_pdv/core/update/pdv_update_service.dart';

void main() {
  test('prepara bundle ao lado da instalação e gera helper com rollback', () async {
    final root = await Directory.systemTemp.createTemp('pdv-installer-');
    final install = Directory('${root.path}${Platform.pathSeparator}current');
    final data = Directory('${root.path}${Platform.pathSeparator}data');
    await install.create();
    AppPaths.overrideDataDirectory(data);
    final executableName = Platform.isWindows
        ? 'starchef_pdv.exe'
        : 'starchef_pdv';
    final currentExecutable = File(
      '${install.path}${Platform.pathSeparator}$executableName',
    );
    await currentExecutable.writeAsString('versão anterior');

    final archive = Archive()
      ..addFile(ArchiveFile.bytes(executableName, [1, 2, 3, 4]))
      ..addFile(
        ArchiveFile.bytes('data/flutter_assets/AssetManifest.bin', [5]),
      );
    final zipBytes = ZipEncoder().encode(archive);
    final zip = File('${root.path}${Platform.pathSeparator}pdv.zip');
    await zip.writeAsBytes(zipBytes);
    final artifact = PdvReleaseArtifact(
      kind: 'portable',
      format: 'zip',
      name: 'pdv.zip',
      url: Uri.parse('https://updates.example/pdv.zip'),
      sha256: sha256.convert(zipBytes).toString(),
      size: zipBytes.length,
      recommended: true,
    );

    final prepared = await PdvUpdateInstaller(
      executable: currentExecutable,
    ).prepare(PdvDownloadedArtifact(artifact: artifact, file: zip), '1.2.3');

    expect(
      prepared.stagingDirectory.path,
      startsWith('${install.path}.starchef-new-'),
    );
    expect(
      File(
        '${prepared.stagingDirectory.path}${Platform.pathSeparator}$executableName',
      ).existsSync(),
      isTrue,
    );
    final helper = await prepared.helperScript.readAsString();
    expect(helper, contains('rollback'));
    expect(helper, contains(install.path));
    final syntax = Platform.isWindows
        ? await Process.run('powershell.exe', [
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            r'$errors=$null; [System.Management.Automation.Language.Parser]'
                "::ParseFile('${prepared.helperScript.path.replaceAll("'", "''")}',"
                r'[ref]$null,[ref]$errors) > $null; '
                r'if ($errors.Count -gt 0) { $errors | Out-String; exit 1 }',
          ])
        : await Process.run('/bin/sh', ['-n', prepared.helperScript.path]);
    expect(syntax.exitCode, isZero, reason: '${syntax.stderr}${syntax.stdout}');

    AppPaths.overrideDataDirectory(null);
    await root.delete(recursive: true);
  });

  test(
    'rejeita pacote EXE porque ele não permite rollback transacional',
    () async {
      final artifact = PdvReleaseArtifact(
        kind: 'installer',
        format: 'exe',
        name: 'setup.exe',
        url: Uri.parse('https://updates.example/setup.exe'),
        sha256: 'a' * 64,
        size: 10,
        recommended: true,
      );

      await expectLater(
        PdvUpdateInstaller().prepare(
          PdvDownloadedArtifact(artifact: artifact, file: File('setup.exe')),
          '1.2.3',
        ),
        throwsFormatException,
      );
    },
  );
}
