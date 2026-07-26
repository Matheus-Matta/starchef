import 'dart:convert';
import 'dart:io';

import '../../../core/network/api_client.dart';

class PrintTemplateCache {
  PrintTemplateCache({required this.api});

  final ApiClient api;

  Future<void> sync({
    required String token,
    required String restaurantId,
  }) async {
    if (!Platform.isWindows) return;
    final response = await api.get('/printers/templates/', accessToken: token);
    final templates = ((response['templates'] ?? const []) as List)
        .cast<Map<String, dynamic>>();
    final root = await _cacheDirectory(restaurantId);
    final manifest = <Map<String, dynamic>>[];
    for (final template in templates) {
      final key = _safeName('${template['key']}');
      if (key.isEmpty) continue;
      final file = File('${root.path}${Platform.pathSeparator}$key.html');
      await _atomicWrite(file, '${template['content'] ?? ''}');
      manifest.add({
        'key': key,
        'template_name': template['template_name'],
        'job_types': template['job_types'],
        'version': template['version'],
        'file': file.path,
      });
    }
    await _atomicWrite(
      File('${root.path}${Platform.pathSeparator}manifest.json'),
      const JsonEncoder.withIndent('  ').convert({
        'restaurant_id': restaurantId,
        'updated_at': DateTime.now().toUtc().toIso8601String(),
        'templates': manifest,
      }),
    );
  }

  Future<Directory> _cacheDirectory(String restaurantId) async {
    final localAppData = Platform.environment['LOCALAPPDATA'];
    final base = localAppData == null || localAppData.trim().isEmpty
        ? Directory.systemTemp
        : Directory(localAppData);
    final directory = Directory(
      '${base.path}${Platform.pathSeparator}StarChef'
      '${Platform.pathSeparator}print_templates'
      '${Platform.pathSeparator}${_safeName(restaurantId)}',
    );
    await directory.create(recursive: true);
    return directory;
  }

  Future<void> _atomicWrite(File destination, String content) async {
    final temporary = File('${destination.path}.tmp');
    await temporary.writeAsString(content, encoding: utf8, flush: true);
    if (await destination.exists()) await destination.delete();
    await temporary.rename(destination.path);
  }

  String _safeName(String value) =>
      value.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '');
}
