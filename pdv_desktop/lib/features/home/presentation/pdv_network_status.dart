import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import 'pdv_status_indicators.dart';

/// Os dois selos de rede da barra: o servidor local e a nuvem.
///
/// Quando a loja cai e quem atende é a nuvem, o operador sabe por aqui — o
/// selo que dizia "Nuvem não monitorada" passa a dizer "Conectado à nuvem", e
/// o do servidor local deixa de dizer "Servidor local". Era uma faixa azul
/// atravessada na tela, que foi tirada a pedido.
class PdvNetworkStatus extends StatelessWidget {
  const PdvNetworkStatus({
    super.key,
    required this.network,
    required this.syncPending,
  });

  final NetworkStatus network;
  final bool syncPending;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final nuvem = network.servidoPelaNuvem;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        PdvStatusIndicator(
          icon: network.hasConnection && !nuvem
              ? Icons.lan_outlined
              : Icons.link_off_outlined,
          label: nuvem
              ? 'Sem servidor local'
              : network.hasConnection
              ? 'Servidor local'
              : 'Sem servidor',
          tone: network.hasConnection && !nuvem
              ? const Color(0xFF166534)
              : scheme.error,
        ),
        const SizedBox(width: 14),
        // Quem atende é a nuvem: o selo diz isso, sem faixa atravessada na
        // tela. Nota fiscal e caixa não desviam para a nuvem de propósito
        // (dois emissores de número de nota não se resolvem com
        // sincronização), por isso o detalhe fica na dica do selo.
        Tooltip(
          message: nuvem
              ? 'O servidor da loja não responde: as vendas estão sendo '
                    'gravadas na nuvem e descem quando ele voltar. Nota '
                    'fiscal e caixa ficam indisponíveis até lá.'
              : '',
          child: PdvStatusIndicator(
            icon: syncPending
                ? Icons.cloud_upload_outlined
                : nuvem
                ? Icons.cloud_done_outlined
                : Icons.cloud_outlined,
            label: syncPending
                ? 'Sincronização pendente'
                : nuvem
                ? 'Conectado à nuvem'
                : 'Nuvem não monitorada',
            tone: syncPending
                ? const Color(0xFF9A5B00)
                : nuvem
                ? const Color(0xFF1D4ED8)
                : scheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}
