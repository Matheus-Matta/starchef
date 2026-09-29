import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_auto_updater.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_update_service.dart';

class _SequencedService extends PdvUpdateService {
  _SequencedService(this.results);

  final List<PdvUpdateStatus> results;
  var checks = 0;

  @override
  Future<PdvUpdateStatus> check({
    void Function(PdvInstalledVersion installed)? onInstalled,
  }) async {
    checks++;
    return results.removeAt(0);
  }

  @override
  void dispose() {}
}

void main() {
  test(
    'busca manual repete a consulta depois da tentativa automatica',
    () async {
      final service = _SequencedService([
        const PdvUpdateStatus(
          phase: PdvUpdatePhase.unavailable,
          detail: 'Sem rede',
        ),
        const PdvUpdateStatus(
          phase: PdvUpdatePhase.upToDate,
          installed: PdvInstalledVersion(version: '3.0.57'),
          latestVersion: '3.0.57',
        ),
      ]);
      final updater = PdvAutoUpdater(service: service, enabled: true);

      await updater.start(closePdv: () async {});
      await updater.checkAndInstall(closePdv: () async {});

      expect(service.checks, 2);
      expect(updater.phase, PdvAutoUpdatePhase.upToDate);
      updater.dispose();
    },
  );
}
