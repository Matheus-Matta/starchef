part of 'pdv_auto_updater.dart';

/// Escolher a versão do PDV: listar as publicadas e instalar uma delas.
///
/// Em parte separada porque é uma responsabilidade própria — voltar a uma
/// versão anterior e FIXÁ-LA (`VersaoFixada`) —, e usa o mesmo caminho de
/// troca da atualização (`trocarDeVersao`).
extension PdvVersaoEscolhida on PdvAutoUpdater {
  /// As versões publicadas que este terminal pode instalar.
  Future<List<PdvVersaoDisponivel>> listarVersoes() => _service.listarVersoes();

  /// Instala [versao] (mais antiga ou mais nova) e a FIXA neste terminal.
  Future<void> instalarVersao(
    PdvVersaoDisponivel versao, {
    required Future<void> Function() closePdv,
  }) async {
    if (_running) return;
    _running = true;
    final anterior = _fixada.ler();
    _setPhase(PdvAutoUpdatePhase.checking);
    try {
      final manifesto = await _service.manifestDe(versao.manifestUrl);
      final artifact = manifesto.automaticArtifactFor(_service.platform);
      if (artifact == null) {
        throw FormatException(
          'A versão ${versao.version} não tem pacote para ${_service.platform}',
        );
      }
      await _fixada.gravar(versao.version);
      await _trocar(artifact, versao.version, closePdv);
    } catch (error, stackTrace) {
      await _fixada.gravar(anterior);
      _falhou(error, stackTrace, versao.version);
    } finally {
      _running = false;
    }
  }
}
