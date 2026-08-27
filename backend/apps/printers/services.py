from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.codes import barcode_data_uri
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.printers.models import Printer, PrintJob

# Mapa explicito job_type -> template. Evita heuristica fragil por substring
# (weigh_ticket e kitchen_ticket ambos contem "ticket").
_TEMPLATE_BY_TYPE = {
    PrintJob.TYPE_KITCHEN: "printers/kitchen_ticket.html",
    PrintJob.TYPE_BAR: "printers/kitchen_ticket.html",
    PrintJob.TYPE_KITCHEN_CANCEL: "printers/kitchen_ticket.html",
    PrintJob.TYPE_WEIGH: "printers/weigh_ticket.html",
    PrintJob.TYPE_RECEIPT: "printers/receipt.html",
    PrintJob.TYPE_TABLE_BILL: "printers/receipt.html",
    PrintJob.TYPE_CASH_CLOSE: "printers/receipt.html",
}
_WITH_PAYMENTS = {PrintJob.TYPE_RECEIPT}

# 42 colunas: largura de Fonte A mais compativel entre as impressoras
# termicas genericas de 80mm vendidas no Brasil. 48 colunas parecia certo no
# papel, mas varias dessas impressoras so cabem 42~47 caracteres reais por
# linha nessa fonte — o excedente nao trunca, ele QUEBRA pra linha de baixo,
# entao um cupom de 48 colunas cortava o ultimo digito do valor pra uma linha
# vazia só com "0". 42 fica seguro mesmo nas mais estreitas, ao custo de
# alguma margem em branco nas impressoras que realmente tem 48 colunas.
LARGURA_CUPOM = 42
_COLUNA_VALOR = 14
# A comanda de producao usa 32 colunas: ela sai em fonte expandida na cozinha,
# entao cabe menos texto por linha do que no cupom do cliente.
LARGURA_COMANDA = 32

# `Order.TYPE_CHOICES` guarda rotulos em ingles (e nem lista `table`), entao
# `get_order_type_display()` imprimiria "TABLE" na comanda da cozinha.
TIPO_ATENDIMENTO_COMANDA = {
    "table": "MESA",
    "command": "COMANDA",
    "counter": "BALCAO",
    "delivery": "DELIVERY",
    "takeaway": "RETIRADA",
}


def _linha_valor(rotulo, valor):
    """Linha com rotulo a esquerda e valor em reais a direita, alinhada em
    LARGURA_CUPOM colunas — o mesmo formato usado em toda linha de item,
    subtotal, total e pagamento do cupom."""
    quantia = f"R$ {valor}"
    largura_rotulo = LARGURA_CUPOM - _COLUNA_VALOR
    rotulo = str(rotulo)[:largura_rotulo]
    return f"{rotulo:<{largura_rotulo}}{quantia:>{_COLUNA_VALOR}}"


def _establishment_info(order):
    """Dados do estabelecimento pro cabecalho do cupom.

    Prioriza os campos da filial: cada unidade fisica costuma ter CNPJ,
    inscricao estadual e endereco proprios para fins de nota, distintos da
    matriz. Cai para os dados da conta (restaurant) quando a filial nao
    tiver o campo preenchido.
    """
    restaurant = order.restaurant
    branch = order.branch

    def pick(field):
        branch_value = getattr(branch, field, "") if branch else ""
        return branch_value or getattr(restaurant, field, "") or ""

    return {
        "legal_name": restaurant.legal_name,
        "trade_name": restaurant.trade_name,
        "cnpj": pick("cnpj"),
        "state_registration": pick("state_registration"),
        "phone": pick("phone"),
        "address": pick("address"),
        "city": pick("city"),
        "state": pick("state"),
        "zip_code": pick("zip_code"),
    }


def _order_command_barcode(order):
    """Codigo de barras (Code128) da comanda do pedido, se houver.

    Usado tanto na nota de pesagem quanto no cupom normal: em ambos, quando
    o pedido esta vinculado a uma comanda fisica, o codigo sai impresso pra
    permitir reler a comanda depois (reabrir, cobrar) sem digitar nada.
    """
    value = ""
    if order.command_id:
        value = str(order.command.code or order.command.number or "")
    return {
        "symbology": "CODE128",
        "value": value,
        "data_uri": barcode_data_uri(value),
    }


def _establishment_lines(info, width=LARGURA_CUPOM):
    """Cabecalho do cupom com os dados do estabelecimento, em texto monospace.

    Compartilhado entre o cupom normal e a nota de pesagem — as duas notas
    saem da mesma impressora fisica e precisam se identificar do mesmo jeito.
    Mostra so o nome fantasia (nao repete a razao social embaixo: quando as
    duas so diferem por "LTDA"/"ME" no fim, a segunda linha e so ruido).
    """
    lines = [info["trade_name"].center(width)]
    lines.append(f"CNPJ: {info['cnpj'] or '-'}")
    if info["state_registration"]:
        lines.append(f"IE: {info['state_registration']}"[:width])
    address_line = f"{info['address']} {info['city']}/{info['state']}".strip(" /")
    if address_line:
        lines.append(address_line[:width])
    if info["zip_code"]:
        lines.append(f"CEP: {info['zip_code']}"[:width])
    if info["phone"]:
        lines.append(f"Tel: {info['phone']}"[:width])
    return lines


def _order_context_lines(order, width=LARGURA_CUPOM):
    """Linhas que identificam o pedido, especificas por tipo.

    Mesa/comanda so fazem sentido pra atendimento no salao; balcao, retirada
    e delivery mostravam sempre "Mesa: - Comanda: -", que nao diz nada sobre
    o pedido de verdade e ainda escondia pra quem era a entrega.
    """
    if order.order_type == "delivery":
        lines = ["DELIVERY"]
        if order.customer_id:
            lines.append(f"Cliente: {order.customer.name}"[:width])
            if order.customer.phone:
                lines.append(f"Telefone: {order.customer.phone}"[:width])
        if order.delivery_address_id:
            address = order.delivery_address
            street_line = f"{address.street}, {address.number}".strip(", ")
            if address.complement:
                street_line += f" - {address.complement}"
            lines.append(street_line[:width])
            district_line = f"{address.district} - {address.city}/{address.state}".strip(" -")
            lines.append(district_line[:width])
            if address.reference:
                lines.append(f"Ref: {address.reference}"[:width])
        return lines
    if order.order_type == "takeaway":
        lines = ["RETIRADA"]
        if order.customer_id:
            lines.append(f"Cliente: {order.customer.name}"[:width])
            if order.customer.phone:
                lines.append(f"Telefone: {order.customer.phone}"[:width])
        return lines
    if order.order_type == "counter":
        lines = ["BALCAO"]
        if order.customer_id:
            lines.append(f"Cliente: {order.customer.name}"[:width])
        return lines
    table_part = f"Mesa: {order.table.number}" if order.table_id else None
    command_part = f"Comanda: {order.command.code}" if order.command_id else None
    if table_part and command_part:
        return [f"{table_part} - {command_part}"[:width]]
    if table_part:
        return [table_part]
    if command_part:
        return [command_part]
    return ["Mesa: - Comanda: -"]


def _customer_receipt_text(order):
    """Converte o recibo web para o equivalente monoespaçado de 80 mm.

    A ordem e o conteúdo seguem ``receipt.html``. Somente recursos exclusivos
    do navegador (CSS, imagem e tags) são substituídos por alinhamento em texto
    e pelo comando ESC/POS de código de barras enviado pelo agente local.
    """
    info = _establishment_info(order)
    lines = [
        info["trade_name"].upper().center(LARGURA_CUPOM),
        "RECIBO DE VENDA - NAO E DOCUMENTO FISCAL".center(LARGURA_CUPOM),
    ]
    document_line = f"CNPJ: {info['cnpj'] or '-'}"
    if info["state_registration"]:
        document_line += f" - IE: {info['state_registration']}"
    lines.append(document_line[:LARGURA_CUPOM])
    address_line = f"{info['address']} {info['city']}".strip()
    if info["state"]:
        address_line += f"/{info['state']}"
    if info["zip_code"]:
        address_line += f" - CEP {info['zip_code']}"
    if address_line:
        lines.append(address_line[:LARGURA_CUPOM])
    if info["phone"]:
        lines.append(f"Telefone: {info['phone']}"[:LARGURA_CUPOM])
    lines.extend(
        [
            "-" * LARGURA_CUPOM,
            f"Pedido nº {order.sequence}",
            *_order_context_lines(order),
        ]
    )
    if order.responsible_user_id:
        operator = order.responsible_user.get_full_name() or order.responsible_user.username
        lines.append(f"Operador: {operator}"[:LARGURA_CUPOM])
    lines.append(f"Data: {timezone.localtime(order.opened_at):%d/%m/%Y %H:%M}")
    lines.append("-" * LARGURA_CUPOM)
    for item in order.items.select_related("product").prefetch_related("addons__addon"):
        if item.status == item.STATUS_CANCELLED:
            continue
        # Produto por peso resolve tudo em uma linha só: repetir a quantidade
        # numa segunda linha ("0,024 kg x ...") mostrava o mesmo peso duas
        # vezes no cupom.
        if item.product.is_weighed:
            descricao = f"{item.quantity:g} x {item.product.name} {item.unit_price}/kg"
        else:
            descricao = f"{item.quantity:g} x {item.product.name}"
        lines.append(_linha_valor(descricao, item.total_price))
    lines.extend(
        [
            "-" * LARGURA_CUPOM,
            _linha_valor("Subtotal", order.subtotal),
            _linha_valor("Serviço", order.service_fee),
            _linha_valor("Desconto", order.discount),
            _linha_valor("Entrega", order.delivery_fee),
            _linha_valor("TOTAL", order.total),
        ]
    )
    payments = order.payments.select_related("payment_method").order_by("created_at")
    if payments.exists():
        lines.extend(["-" * LARGURA_CUPOM, "FORMA(S) DE PAGAMENTO"])
        for payment in payments:
            lines.append(_linha_valor(payment.payment_method.name, payment.amount))
            if payment.change_amount:
                lines.append(_linha_valor("Troco", payment.change_amount))
    barcode_value = _order_command_barcode(order)["value"]
    if barcode_value:
        # So o valor: o agente local (LocalDeviceAgent) reconhece este mesmo
        # payload_version/barcode e imprime o Code128 de verdade no final do
        # cupom — aqui so cabe a legenda legivel, redundante em impressoras
        # sem ESC/POS.
        lines.extend(
            [
                "-" * LARGURA_CUPOM,
                "COMANDA - CODE128".center(LARGURA_CUPOM),
                barcode_value.center(LARGURA_CUPOM),
            ]
        )
    lines.extend(["-" * LARGURA_CUPOM, "Obrigado pela preferência!".center(LARGURA_CUPOM), ""])
    return "\n".join(lines)


def render_print_html(order, job_type, **extra):
    """Renderiza o HTML de um job a partir do template correspondente ao tipo."""
    template = _TEMPLATE_BY_TYPE.get(job_type, "printers/receipt.html")
    context = {"order": order, "items": order.items.select_related("product").all(), **extra}
    if job_type in _WITH_PAYMENTS:
        context["payments"] = order.payments.select_related("payment_method").order_by("created_at")
    return render_to_string(template, context)


def register_print_job(
    *,
    order,
    user,
    job_type=PrintJob.TYPE_RECEIPT,
    printer=None,
    manual_only=False,
):
    with tenant_context(order.account):
        # Compatibilidade com clientes antigos; novos jobs persistem um unico tipo.
        if job_type == "payment_receipt":
            job_type = PrintJob.TYPE_RECEIPT
        if printer and printer.account_id != order.account_id:
            raise ValueError("Printer does not belong to the order account.")
        if printer is None:
            active = Printer.objects.filter(restaurant=order.restaurant, is_active=True)
            if order.branch_id:
                active = active.filter(Q(branch_id=order.branch_id) | Q(branch__isnull=True))
            if job_type in {PrintJob.TYPE_KITCHEN, PrintJob.TYPE_BAR}:
                sector_ids = order.items.exclude(product__sector=None).values_list("product__sector_id", flat=True)
                printer = (
                    active.filter(sector_id__in=sector_ids).order_by("name").first()
                    or active.filter(sector=None).order_by("name").first()
                    or active.order_by("name").first()
                )
            else:
                # Recibo/conta/fechamento preferem uma impressora sem setor,
                # evitando enviar o pedido inteiro a uma cozinha por engano.
                printer = active.filter(sector=None).order_by("name").first()
                if printer is None:
                    # Restaurantes pequenos frequentemente usam uma única
                    # impressora física no caixa e na cozinha. Se só há uma
                    # opção compatível com a filial, a escolha é inequívoca
                    # mesmo que ela esteja vinculada a um setor.
                    candidates = list(active.order_by("name")[:2])
                    if len(candidates) == 1:
                        printer = candidates[0]

        if printer is None:
            if active.exists():
                raise ValidationError(
                    "Há mais de uma impressora setorizada ativa. Cadastre uma "
                    "impressora sem setor para ser o destino automático dos recibos."
                )
            raise ValidationError(
                "Nenhuma impressora ativa foi encontrada para este restaurante e filial."
            )

        barcode = _order_command_barcode(order)
        html = render_print_html(
            order,
            job_type,
            establishment=_establishment_info(order),
            barcode=barcode,
        )
        job = PrintJob.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            printer=printer,
            order=order,
            job_type=job_type,
            status=PrintJob.STATUS_RENDERED,
            payload={
                "account_id": str(order.account_id),
                "order_id": str(order.id),
                "sequence": order.sequence,
                "manual_only": manual_only,
                # payload_version 2 + barcode: mesmo formato que o agente local
                # (LocalDeviceAgent.code128ValueFromPayload) ja sabe reconhecer
                # pra imprimir o Code128 de verdade no final do cupom, sem
                # nenhuma mudanca no cliente.
                "payload_version": 2,
                "barcode": {"symbology": barcode["symbology"], "value": barcode["value"]},
                "text_content": (
                    _customer_receipt_text(order) if job_type in _WITH_PAYMENTS | {PrintJob.TYPE_TABLE_BILL} else ""
                ),
            },
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        record_audit(action=AuditLog.ACTION_PRINTED, instance=job, actor=user, metadata={"job_type": job_type})
        return job


def _kitchen_quantity(value):
    return format(Decimal(value).normalize(), "f")


def _kitchen_two_columns(left, right, width=LARGURA_COMANDA):
    """Rotulo a esquerda e valor a direita na mesma linha da comanda."""
    left, right = str(left), str(right)
    espaco = width - len(left) - len(right)
    if espaco < 1:
        return f"{left} {right}"[:width]
    return f"{left}{' ' * espaco}{right}"


def _kitchen_ticket_text(*, order, batch, sector, items):
    """Comanda de producao: o que a cozinha precisa pra montar o pedido.

    Alem dos itens, identifica de qual pedido/rodada a comanda veio, a que
    horas foi lancada, o tipo de atendimento (salao, balcao, entrega...),
    mesa/comanda, cliente e quem lancou. Sem isso a cozinha recebia uma lista
    solta de produtos, sem saber a origem nem se era pra entrega.
    """
    total_itens = sum((Decimal(item.quantity) for item in items), Decimal("0"))
    enviado_em = batch.sent_at or timezone.now()
    lines = [
        "NOVO PEDIDO".center(LARGURA_COMANDA),
        str(sector.name).upper().center(LARGURA_COMANDA)[:LARGURA_COMANDA],
        "-" * LARGURA_COMANDA,
        _kitchen_two_columns(
            f"PEDIDO #{order.sequence}",
            f"RODADA {batch.batch_number}",
        ),
        timezone.localtime(enviado_em).strftime("%d/%m/%Y %H:%M:%S"),
        "-" * LARGURA_COMANDA,
    ]
    # Balcao/entrega/retirada nao tem mesa nem comanda: sem esta linha a
    # cozinha nao sabe que o pedido nao e do salao. No salao, as linhas de
    # mesa/comanda abaixo ja dizem o tipo, entao repetir seria ruido.
    if order.order_type not in {"table", "command"}:
        lines.append(
            TIPO_ATENDIMENTO_COMANDA.get(order.order_type, str(order.order_type).upper())[:LARGURA_COMANDA]
        )
    if order.table_id:
        lines.append(f"MESA: {order.table.number}"[:LARGURA_COMANDA])
    if order.command_id:
        lines.append(f"COMANDA: {order.command.code}"[:LARGURA_COMANDA])
    if order.customer_id:
        lines.append(f"CLIENTE: {order.customer.name}"[:LARGURA_COMANDA])
    if order.responsible_user_id:
        atendente = order.responsible_user.get_full_name() or order.responsible_user.username
        lines.append(f"ATENDENTE: {atendente}"[:LARGURA_COMANDA])
    lines.append("-" * LARGURA_COMANDA)
    for item in items:
        lines.append(f"{_kitchen_quantity(item.quantity)}x {item.product.name}"[:LARGURA_COMANDA])
        for variation in item.variations or []:
            name = variation.get("name", variation) if isinstance(variation, dict) else variation
            lines.append(f"  VAR: {name}"[:LARGURA_COMANDA])
        for addon in item.addons.all():
            lines.append(f"  + {_kitchen_quantity(addon.quantity)}x {addon.addon.name}"[:LARGURA_COMANDA])
        if item.customer_note:
            lines.append(f"  OBS: {item.customer_note}"[:LARGURA_COMANDA])
        lines.append("-" * LARGURA_COMANDA)
    lines.append(_kitchen_two_columns("TOTAL DE ITENS", _kitchen_quantity(total_itens)))
    # Mantém uma referência curta no rodapé para que um eventual cancelamento
    # posterior possa ser ligado exatamente a esta impressão.
    lines.extend([f"REF: {batch.serial}", ""])
    return "\n".join(lines)


def register_kitchen_batch_print_jobs(*, batch, user, offline_printed=False):
    """Cria um ticket por impressora/setor contendo apenas os itens da rodada.

    ``offline_printed=True`` significa que o PDV já imprimiu essa comanda
    localmente (rede fora quando o pedido foi mandado à cozinha): os
    `PrintJob` continuam sendo criados — a auditoria e o cancelamento
    (`register_kitchen_item_cancellation_jobs`) dependem deles — mas já
    nascem `STATUS_PRINTED`, para o `LocalDeviceAgent` (que só faz polling de
    `scheduled|pending|rendered`) nunca mandar os bytes de novo.
    """
    order = batch.order
    with tenant_context(order.account):
        items = list(
            batch.items.select_related("product__sector")
            .prefetch_related("addons__addon")
            .filter(status="queued")
            .order_by("launched_at")
        )
        by_sector = {}
        for item in items:
            sector = item.product.sector
            if sector is not None:
                by_sector.setdefault(sector.id, {"sector": sector, "items": []})["items"].append(item)

        jobs = []
        for group in by_sector.values():
            sector = group["sector"]
            sector_items = group["items"]
            printers = Printer.objects.filter(
                restaurant=order.restaurant,
                sector=sector,
                is_active=True,
            ).order_by("name")
            for printer in printers:
                html = render_print_html(
                    order,
                    PrintJob.TYPE_KITCHEN,
                    items=sector_items,
                    batch=batch,
                    sector=sector,
                )
                text = _kitchen_ticket_text(
                    order=order,
                    batch=batch,
                    sector=sector,
                    items=sector_items,
                )
                if offline_printed:
                    job_status = PrintJob.STATUS_PRINTED
                elif batch.status == batch.STATUS_SCHEDULED:
                    job_status = PrintJob.STATUS_SCHEDULED
                else:
                    job_status = PrintJob.STATUS_RENDERED
                job = PrintJob.objects.create(
                    account=order.account,
                    restaurant=order.restaurant,
                    branch=order.branch,
                    printer=printer,
                    order=order,
                    job_type=PrintJob.TYPE_KITCHEN,
                    status=job_status,
                    printed_at=timezone.now() if offline_printed else None,
                    available_at=batch.dispatch_at,
                    payload={
                        "account_id": str(order.account_id),
                        "order_id": str(order.id),
                        "sequence": order.sequence,
                        "batch_id": str(batch.id),
                        "batch_number": batch.batch_number,
                        "batch_serial": str(batch.serial),
                        "sector_id": str(sector.id),
                        "sector_name": sector.name,
                        "item_ids": [str(item.id) for item in sector_items],
                        "text_content": text,
                        "offline_printed": offline_printed,
                    },
                    html_content=html,
                    printed_by=user,
                    created_by=user,
                    updated_by=user,
                )
                jobs.append(job)
                record_audit(
                    action=AuditLog.ACTION_PRINTED,
                    instance=job,
                    actor=user,
                    metadata={
                        "job_type": PrintJob.TYPE_KITCHEN,
                        "batch": batch.batch_number,
                        "sector": str(sector.id),
                    },
                )
        return jobs


def refresh_scheduled_kitchen_batch_jobs(*, batch, user):
    """Rebuild a not-yet-released ticket after an item is cancelled.

    The previous immutable jobs remain as cancelled audit evidence and are
    never exposed to the printer agent.
    """
    with tenant_context(batch.account):
        now = timezone.now()
        PrintJob.objects.filter(
            payload__batch_id=str(batch.id),
            status=PrintJob.STATUS_SCHEDULED,
        ).update(status=PrintJob.STATUS_CANCELLED, updated_at=now)
        if not batch.items.filter(status="queued").exists():
            batch.status = batch.STATUS_CANCELLED
            batch.save(update_fields=["status", "updated_at"])
            return []
        jobs = register_kitchen_batch_print_jobs(batch=batch, user=user)
        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=batch,
            actor=user,
            metadata={
                "event": "scheduled_kitchen_ticket_rebuilt",
                "batch_serial": str(batch.serial),
                "printed_cancellation": False,
            },
        )
        return jobs


def _kitchen_cancellation_text(*, item, original_job, reason):
    order = item.order
    batch = item.batch
    where = (
        f"Mesa {order.table.number}"
        if order.table_id
        else (f"Comanda {order.command.code}" if order.command_id else order.get_order_type_display())
    )
    return "\n".join(
        [
            "CANCELAMENTO".center(32),
            f"PEDIDO #{order.sequence}".center(32),
            f"ORIGINAL {original_job.serial}".center(32),
            f"RODADA {batch.serial if batch else '-'}".center(32),
            "-" * 32,
            where,
            f"CANCELAR {_kitchen_quantity(item.quantity)}x {item.product.name}"[:32],
            f"MOTIVO: {reason}"[:32],
            timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"),
            "-" * 32,
            "FIM DO CANCELAMENTO".center(32),
            "",
        ]
    )


def register_kitchen_item_cancellation_jobs(*, item, user, reason):
    """Create one immediate, idempotent cancellation per original ticket."""
    with tenant_context(item.account):
        originals = PrintJob.objects.filter(
            order=item.order,
            job_type=PrintJob.TYPE_KITCHEN,
        ).exclude(status=PrintJob.STATUS_CANCELLED)
        originals = [
            job
            for job in originals
            if str(job.payload.get("batch_id", "")) == str(item.batch_id)
            and str(item.id) in {str(value) for value in job.payload.get("item_ids", [])}
        ]
        jobs = []
        for original in originals:
            text = _kitchen_cancellation_text(item=item, original_job=original, reason=reason)
            job, created = PrintJob.objects.get_or_create(
                original_job=original,
                cancelled_item=item,
                defaults={
                    "account": item.account,
                    "restaurant": item.restaurant,
                    "branch": item.branch,
                    "printer": original.printer,
                    "order": item.order,
                    "job_type": PrintJob.TYPE_KITCHEN_CANCEL,
                    "status": PrintJob.STATUS_RENDERED,
                    "available_at": timezone.now(),
                    "payload": {
                        "account_id": str(item.account_id),
                        "order_id": str(item.order_id),
                        "original_print_serial": str(original.serial),
                        "batch_serial": str(item.batch.serial) if item.batch_id else "",
                        "cancelled_item_id": str(item.id),
                        "reason": reason,
                        "text_content": text,
                    },
                    "printed_by": user,
                    "created_by": user,
                    "updated_by": user,
                },
            )
            jobs.append(job)
            if created:
                record_audit(
                    action=AuditLog.ACTION_PRINTED,
                    instance=job,
                    actor=user,
                    reason=reason,
                    metadata={
                        "event": "kitchen_cancellation_scheduled",
                        "original_print_serial": str(original.serial),
                        "cancelled_item_id": str(item.id),
                    },
                )
        return jobs


def register_printer_test_job(*, printer, user):
    """Gera uma nota de teste sem dispará-la automaticamente."""
    with tenant_context(printer.account):
        hidden_terms = ("password", "secret", "token", "senha", "chave")
        safe_settings = {
            key: value
            for key, value in (printer.settings or {}).items()
            if not any(term in str(key).lower() for term in hidden_terms)
        }
        sector = printer.sector.name if printer.sector_id else "Todos os setores"
        mode = "Ativada" if printer.auto_print else "Desativada"
        active = "Ativa" if printer.is_active else "Inativa"
        lines = [
            "STARCHEF PDV".center(32),
            "TESTE DE IMPRESSORA".center(32),
            "-" * 32,
            f"Nome: {printer.name}",
            f"Driver: {printer.get_driver_type_display()}",
            f"Conexao: {printer.get_connection_type_display()}",
            f"Windows/Serial: {printer.endpoint or 'Nao configurado'}",
            f"IP: {printer.host or 'Nao configurado'}",
            f"Porta TCP: {printer.port}",
            f"Timeout: {printer.timeout_seconds}s",
            f"Setor: {sector}",
            f"Impressao automatica: {mode}",
            f"Status: {active}",
            f"Executor: {safe_settings.get('executor', 'Nao informado')}",
        ]
        for key, value in sorted(safe_settings.items()):
            if key != "executor":
                lines.append(f"{key}: {value}")
        lines.extend(
            [
                "-" * 32,
                timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"),
                "CONEXAO REALIZADA".center(32),
                "",
            ]
        )
        text = "\n".join(lines)
        html = f"<pre>{text}</pre>"
        job = PrintJob.objects.create(
            account=printer.account,
            restaurant=printer.restaurant,
            branch=printer.branch,
            printer=printer,
            job_type="printer_test",
            status=PrintJob.STATUS_RENDERED,
            payload={"text_content": text, "diagnostic": True},
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        return job


# ── Nota de pesagem (balanca por kilo) ─────────────────────────────────────
def _resolve_weigh_printer(*, order, scale):
    """Resolve somente uma impressora explicitamente configurada na balanca.

    ``Printer`` ainda nao possui campo/constraint de impressora padrao. Escolher
    a primeira impressora ativa do restaurante seria ambiguo e poderia enviar a
    nota para outro caixa ou setor.
    """
    if scale is None or not scale.printer_id:
        raise ValidationError(
            "Balanca sem impressora ativa configurada; o modelo atual nao define "
            "uma impressora padrao segura para fallback."
        )

    printer = Printer.objects.filter(
        pk=scale.printer_id,
        account=order.account,
        restaurant=order.restaurant,
        is_active=True,
    ).first()
    same_branch = not (printer and scale.branch_id and printer.branch_id and printer.branch_id != scale.branch_id)
    if printer is None or not same_branch:
        raise ValidationError(
            "A impressora configurada na balanca esta inativa ou fora do mesmo " "restaurante/filial."
        )
    return printer


def _weigh_ticket_items(order):
    excluded = {"cancelled", "comped"}
    return list(order.items.select_related("product").exclude(status__in=excluded).order_by("launched_at", "id"))


def _weigh_ticket_payload(*, order, weighed_item, items, barcode):
    command = None
    if order.command_id:
        command = {
            "id": str(order.command_id),
            "number": order.command.number,
            "code": order.command.code,
        }

    serialized_items = [
        {
            "id": str(ticket_item.id),
            "product_id": str(ticket_item.product_id),
            "name": ticket_item.product.name,
            "pricing_unit": ticket_item.product.pricing_unit,
            "is_weighed": ticket_item.product.is_weighed,
            "quantity": str(ticket_item.quantity),
            "unit_price": str(ticket_item.unit_price),
            "total": str(ticket_item.total_price),
        }
        for ticket_item in items
    ]
    return {
        "payload_version": 2,
        # Campos legados do item pesado, preservados para agentes ja instalados.
        "order_id": str(order.id),
        "item_id": str(weighed_item.id),
        "sequence": order.sequence,
        "weight_kg": str(weighed_item.quantity),
        "unit_price": str(weighed_item.unit_price),
        "total": str(weighed_item.total_price),
        "item_total": str(weighed_item.total_price),
        # Snapshot completo e autocontido da nota.
        "restaurant": {
            "id": str(order.restaurant_id),
            "trade_name": order.restaurant.trade_name,
            "legal_name": order.restaurant.legal_name,
            "cnpj": order.restaurant.cnpj,
        },
        "order": {
            "id": str(order.id),
            "sequence": order.sequence,
            "type": order.order_type,
            "command": command,
            "subtotal": str(order.subtotal),
            "total": str(order.total),
        },
        "command": command,
        "items": serialized_items,
        "subtotal": str(order.subtotal),
        "order_total": str(order.total),
        "barcode": {
            "symbology": barcode["symbology"],
            "value": barcode["value"],
        },
    }


def _weigh_ticket_text(*, order, weighed_item, items, barcode):
    """Versao texto (monospace) da nota, enviada pelo agente para impressoras ESC/POS."""
    where = (
        f"Mesa {order.table.number}"
        if order.table_id
        else (f"Comanda {order.command.code}" if order.command_id else "Balcao")
    )
    lines = _establishment_lines(_establishment_info(order))
    lines.extend(
        [
            "NOTA DE PESAGEM".center(LARGURA_CUPOM),
            "-" * LARGURA_CUPOM,
            f"Pedido #{order.sequence}  {where}",
            timezone.localtime(weighed_item.created_at).strftime("%d/%m/%Y %H:%M"),
            "-" * LARGURA_CUPOM,
        ]
    )
    for ticket_item in items:
        lines.append(_linha_valor(ticket_item.product.name, ticket_item.total_price))
        if ticket_item.product.is_weighed:
            lines.append(f"{Decimal(ticket_item.quantity):.3f} kg x " f"R$ {ticket_item.unit_price}/kg")
        else:
            lines.append(f"{ticket_item.quantity:g} un x R$ {ticket_item.unit_price}")
        lines.append("-" * LARGURA_CUPOM)
    lines.append(_linha_valor("TOTAL DO PEDIDO", order.total))
    if barcode["value"]:
        lines.extend(
            [
                "",
                "COMANDA - CODE128".center(LARGURA_CUPOM),
                barcode["value"].center(LARGURA_CUPOM),
            ]
        )
    lines.extend(["", "Pague no caixa. Obrigado!".center(LARGURA_CUPOM)])
    return "\n".join(lines)


def register_weigh_print(*, order, item, scale, user=None):
    """Gera a nota de pesagem (HTML + texto) como PrintJob PENDENTE na impressora da balanca.

    Fica pendente ate o agente local imprimir e chamar mark-printed. Como o modelo
    nao identifica uma impressora padrao, exige uma impressora ativa configurada
    explicitamente na balanca.
    """
    with tenant_context(order.account):
        printer = _resolve_weigh_printer(order=order, scale=scale)
        order.refresh_from_db(
            fields=[
                "subtotal",
                "service_fee",
                "discount",
                "delivery_fee",
                "total",
            ]
        )
        items = _weigh_ticket_items(order)
        barcode = _order_command_barcode(order)
        payload = _weigh_ticket_payload(
            order=order,
            weighed_item=item,
            items=items,
            barcode=barcode,
        )
        payload["text_content"] = _weigh_ticket_text(
            order=order,
            weighed_item=item,
            items=items,
            barcode=barcode,
        )
        html = render_print_html(
            order,
            PrintJob.TYPE_WEIGH,
            item=item,
            scale=scale,
            items=items,
            barcode=barcode,
            establishment=_establishment_info(order),
        )
        job = PrintJob.objects.create(
            account=order.account,
            restaurant=order.restaurant,
            branch=order.branch,
            printer=printer,
            order=order,
            job_type=PrintJob.TYPE_WEIGH,
            status=PrintJob.STATUS_PENDING,
            payload=payload,
            html_content=html,
            printed_by=user,
            created_by=user,
            updated_by=user,
        )
        record_audit(
            action=AuditLog.ACTION_PRINTED, instance=job, actor=user, metadata={"job_type": PrintJob.TYPE_WEIGH}
        )
        return job


@transaction.atomic
def weigh_to_order(*, scale, order, user, scale_reading=None, weight_kg=None, do_print=True):
    """Fluxo principal: pesa -> lanca item por kg no pedido -> gera a nota de pesagem.

    Retorna (item, print_job). `print_job` e None quando `do_print=False`.
    """
    # Import tardio evita ciclo entre apps.orders.services e apps.printers.services.
    from apps.orders.services import add_order_item

    if not scale.product_id:
        raise ValidationError("Balanca sem produto por kilo configurado.")
    if order.account_id != scale.account_id:
        raise ValidationError("Pedido e balanca pertencem a contas diferentes.")
    if order.restaurant_id != scale.restaurant_id:
        raise ValidationError("Pedido e balanca pertencem a restaurantes diferentes.")
    if do_print:
        # Falha antes de consumir a leitura/criar o item. A transacao tambem
        # protege contra qualquer erro posterior durante a renderizacao do job.
        _resolve_weigh_printer(order=order, scale=scale)

    item = add_order_item(
        order=order,
        product=scale.product,
        user=user,
        scale_reading=scale_reading,
        weight_kg=weight_kg,
    )
    job = register_weigh_print(order=order, item=item, scale=scale, user=user) if do_print else None
    return item, job
