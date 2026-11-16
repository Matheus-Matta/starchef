"""NSU de consulta da distribuição DF-e, ajustado à mão (`/inbound-nfe/set-nsu/`).

Fora de `views.py`, que passava de mil linhas. Também limpa o bloqueio de
intervalo (`next_allowed_at`) e o contador de erros, para a próxima
sincronização partir do NSU informado.
"""
import re

from rest_framework import status
from rest_framework.response import Response

from apps.inbound_nfe.models import DFeSyncState
from apps.inbound_nfe.tenant_scope import restaurante_escolhido
from apps.invoices.models import FiscalConfig


def gravar_nsu_manual(request):
    nsu_raw = request.data.get("ult_nsu")
    if nsu_raw is None:
        nsu_raw = request.data.get("nsu")
    if nsu_raw is None:
        return Response({"error": "Campo 'ult_nsu' é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)
    # NSU é número de até 15 dígitos; lixo gravado aqui quebra a próxima consulta à SEFAZ.
    nsu_texto = str(nsu_raw).strip() if isinstance(nsu_raw, (str, int)) and not isinstance(nsu_raw, bool) else ""
    if not re.fullmatch(r"\d{1,15}", nsu_texto):
        return Response({"error": "NSU inválido: informe só números, até 15 dígitos."},
                        status=status.HTTP_400_BAD_REQUEST)
    clean_nsu = nsu_texto.zfill(15)

    restaurant_id = restaurante_escolhido(request)

    config = None
    if restaurant_id:
        config = FiscalConfig.objects.filter(
            account=request.account,
            restaurant_id=restaurant_id
        ).first()

    if not config:
        config = (
            FiscalConfig.objects.filter(account=request.account, is_active=True).first()
            or FiscalConfig.objects.filter(account=request.account).first()
        )

    cnpj = re.sub(r'\D', '', (config.cnpj if config else '') or (config.certificate_cnpj if config else '') or '')

    # O estado da distribuição é POR RESTAURANTE (coluna obrigatória): sem
    # perfil fiscal, vale o restaurante escolhido; sem nenhum dos dois, não
    # há a quem atribuir o NSU (antes: IntegrityError).
    restaurante = (config.restaurant_id if config else None) or restaurant_id
    if not restaurante:
        return Response({"error": "Escolha o restaurante do NSU."}, status=status.HTTP_400_BAD_REQUEST)

    state = DFeSyncState.objects.filter(account=request.account, restaurant_id=restaurante).first()
    if not state:
        state, _ = DFeSyncState.objects.get_or_create(
            account=request.account,
            branch=config.branch if config else None,
            restaurant_id=restaurante,
            defaults={
                'cnpj': cnpj,
                'ult_nsu': clean_nsu,
            }
        )
    state.ult_nsu = clean_nsu
    state.next_allowed_at = None
    state.sync_error_count = 0
    state.save(update_fields=['ult_nsu', 'next_allowed_at', 'sync_error_count'])
    return Response({"status": "ok", "ult_nsu": state.ult_nsu})
