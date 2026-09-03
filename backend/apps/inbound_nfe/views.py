from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from apps.core.viewsets import BaseTenantViewSet
from apps.inbound_nfe.models import (
    InboundNFe,
    InboundNFeItem,
    SupplierItemMapping,
    DFeDistributionDocument,
    DFeSyncState,
)
from apps.inbound_nfe.serializers import (
    InboundNFeSerializer,
    InboundNFeItemMapRequestSerializer,
    ReceiveInvoiceRequestSerializer,
    DFeDistributionDocumentSerializer,
    DFeSyncStateSerializer,
)
from apps.inbound_nfe.services.receiving import receive_invoice
from apps.inbound_nfe.services.manifestation import manifest_nfe
import django_filters
from apps.stock.models import StockLocation
from apps.menu.models import Ingredient, Product


class InboundNFeFilterSet(django_filters.FilterSet):
    issue_date_after = django_filters.DateFilter(field_name="issue_date", lookup_expr="date__gte")
    issue_date_before = django_filters.DateFilter(field_name="issue_date", lookup_expr="date__lte")
    issue_date = django_filters.DateFilter(field_name="issue_date", lookup_expr="date")

    number = django_filters.CharFilter(field_name="number", lookup_expr="icontains")
    series = django_filters.CharFilter(field_name="series", lookup_expr="exact")
    access_key = django_filters.CharFilter(field_name="access_key", lookup_expr="icontains")
    supplier_name = django_filters.CharFilter(field_name="supplier_name", lookup_expr="icontains")
    supplier_cnpj = django_filters.CharFilter(field_name="supplier_cnpj", lookup_expr="icontains")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    nsu = django_filters.CharFilter(field_name="nsu", lookup_expr="exact")
    restaurant = django_filters.UUIDFilter(field_name="restaurant", lookup_expr="exact")
    mapping_filter = django_filters.CharFilter(method="filter_by_mapping")

    class Meta:
        model = InboundNFe
        fields = [
            "status",
            "supplier_cnpj",
            "supplier_name",
            "number",
            "series",
            "access_key",
            "nsu",
            "issue_date",
            "issue_date_after",
            "issue_date_before",
            "restaurant",
            "mapping_filter",
        ]

    def filter_by_mapping(self, queryset, name, value):
        if value == "unmapped":
            return queryset.filter(status=InboundNFe.STATUS_PENDING_MAPPING)
        elif value == "ready":
            return queryset.filter(status=InboundNFe.STATUS_PENDING_RECEIPT)
        elif value in ("received", "finalized"):
            return queryset.filter(status=InboundNFe.STATUS_RECEIVED)
        elif value == "summary":
            return queryset.filter(status=InboundNFe.STATUS_SUMMARY)
        return queryset


class InboundNFeViewSet(BaseTenantViewSet):
    queryset = InboundNFe.objects.all()
    serializer_class = InboundNFeSerializer
    filterset_class = InboundNFeFilterSet
    search_fields = [
        "number",
        "series",
        "access_key",
        "supplier_name",
        "supplier_cnpj",
        "nsu",
        "items__description",
        "items__supplier_code",
        "items__ean",
    ]
    ordering_fields = ["issue_date", "created_at", "total_invoice", "number", "supplier_name", "status", "nsu"]
    ordering = ["-issue_date", "-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        mapping_filter = (
            self.request.query_params.get("mapping_filter")
            or self.request.query_params.get("filter_status")
            or self.request.query_params.get("filter")
        )
        if mapping_filter == "unmapped":
            qs = qs.filter(status=InboundNFe.STATUS_PENDING_MAPPING)
        elif mapping_filter == "ready":
            qs = qs.filter(status=InboundNFe.STATUS_PENDING_RECEIPT)
        elif mapping_filter in ("received", "finalized"):
            qs = qs.filter(status=InboundNFe.STATUS_RECEIVED)
        elif mapping_filter == "summary":
            qs = qs.filter(status=InboundNFe.STATUS_SUMMARY)
        return qs.distinct()

    @action(detail=False, methods=["get"], url_path="status-counts")
    def status_counts(self, request, *args, **kwargs):
        """Retorna a contagem de notas por status para alimentar os filtros."""
        from django.db.models import Count
        base_qs = super().get_queryset()
        restaurant_id = request.query_params.get("restaurant")
        if restaurant_id:
            base_qs = base_qs.filter(restaurant_id=restaurant_id)

        issue_after = request.query_params.get("issue_date_after")
        issue_before = request.query_params.get("issue_date_before")
        if issue_after:
            base_qs = base_qs.filter(issue_date__date__gte=issue_after)
        if issue_before:
            base_qs = base_qs.filter(issue_date__date__lte=issue_before)

        counts = dict(
            base_qs.values("status").annotate(total=Count("id")).values_list("status", "total")
        )
        total_all = sum(counts.values())
        return Response({
            "all": total_all,
            "unmapped": counts.get(InboundNFe.STATUS_PENDING_MAPPING, 0),
            "ready": counts.get(InboundNFe.STATUS_PENDING_RECEIPT, 0),
            "received": counts.get(InboundNFe.STATUS_RECEIVED, 0),
            "summary": counts.get(InboundNFe.STATUS_SUMMARY, 0),
        })

    @action(detail=False, methods=["post", "get"])
    def sync(self, request, *args, **kwargs):
        """Executa ou consulta o status da sincronização com a SEFAZ."""
        import re
        from django.utils import timezone
        from datetime import timedelta
        from apps.invoices.models import FiscalConfig
        from apps.inbound_nfe.models import DFeSyncState, DFeGlobalConfig
        from apps.inbound_nfe.tasks import _perform_sync

        restaurant_id = (
            request.data.get("restaurant")
            or request.query_params.get("restaurant")
            or request.headers.get("X-Restaurant-ID")
            or request.headers.get("x-restaurant-id")
            or request.META.get("HTTP_X_RESTAURANT_ID")
            or getattr(getattr(request.user, "profile", None), "restaurant_id", None)
        )

        from apps.restaurants.models import Restaurant

        # Visão consolidada: "Todos os Restaurantes" (sem filtro específico de restaurante)
        if not restaurant_id:
            if request.method == "POST":
                return Response(
                    {"error": "Selecione um restaurante específico na barra lateral para sincronizar com a SEFAZ."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            latest_state = DFeSyncState.all_objects.filter(account=request.account).order_by("-last_sync_at").first()
            return Response({
                "status": "all_restaurants",
                "is_all_restaurants": True,
                "restaurant_name": "Todos os Restaurantes",
                "last_sync_at": latest_state.last_sync_at if latest_state else None,
                "sync_interval_hours": 3,
                "message": "Visualizando todas as unidades. Cada restaurante possui seu próprio controle de NSU e certificado digital.",
                "invoices_count": InboundNFe.objects.filter(account=request.account).count(),
            })

        restaurant_obj = Restaurant.all_objects.filter(id=restaurant_id, account=request.account).first()
        config = FiscalConfig.all_objects.filter(
            account=request.account,
            restaurant_id=restaurant_id
        ).first()

        restaurant_name = (
            (restaurant_obj.trade_name if restaurant_obj else None)
            or (config.trade_name if config else None)
            or "Restaurante"
        )

        has_cert = bool(config and (config.certificate_file or config.certificate_ref))

        state = DFeSyncState.all_objects.filter(
            account=request.account,
            restaurant_id=restaurant_id
        ).first()

        # Se for GET e não houver certificado, responde 200 informando o estado sem quebrar a tela
        if request.method == "GET" and not has_cert:
            return Response({
                "status": "no_certificate",
                "has_certificate": False,
                "restaurant_id": str(restaurant_id),
                "restaurant_name": restaurant_name,
                "ult_nsu": state.ult_nsu if state else "000000000000000",
                "message": f"Certificado Digital A1 não configurado para '{restaurant_name}'. Acesse o perfil do restaurante para fazer o upload do certificado e definir o NSU inicial.",
                "invoices_count": InboundNFe.objects.filter(account=request.account, restaurant_id=restaurant_id).count(),
            })

        if request.method == "POST" and not has_cert:
            return Response(
                {"error": f"Certificado A1 não configurado para o restaurante '{restaurant_name}'. Acesse o perfil do restaurante e configure o certificado digital."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cnpj = re.sub(r'\D', '', (config.cnpj if config else '') or (config.certificate_cnpj if config else '') or '')
        environment = (
            "homologation"
            if config and config.environment == FiscalConfig.ENV_HOMOLOGATION
            else "production"
        )

        if not state:
            state, _ = DFeSyncState.all_objects.get_or_create(
                account=request.account,
                branch=config.branch if config else None,
                restaurant=config.restaurant if config else restaurant_obj,
                defaults={
                    'cnpj': cnpj,
                    'environment': environment,
                }
            )

        if state.cnpj != cnpj or state.environment != environment or (config and state.restaurant != config.restaurant):
            state.cnpj = cnpj
            state.environment = environment
            if config:
                state.restaurant = config.restaurant
                state.branch = config.branch
            state.save(update_fields=['cnpj', 'environment', 'restaurant', 'branch'])

        now = timezone.now()
        is_blocked = False
        blocked_reason = ""
        minutes_remaining = 0

        global_cfg = DFeGlobalConfig.get_solo()

        # O bloqueio preventivo só é acionado se estiver ativado nas configurações globais
        if global_cfg.enable_cooldown_blocking:
            # Regra 1: Bloqueio por cooldown explícito (ex: cStat 656 ou 137 com next_allowed_at)
            if state.next_allowed_at and state.next_allowed_at > now:
                is_blocked = True
                minutes_remaining = max(1, int((state.next_allowed_at - now).total_seconds() // 60))
                dh_str = state.next_allowed_at.strftime("%H:%M:%S (%d/%m/%Y)")
                template = (
                    global_cfg.blocked_cstat_656_message_template
                    if state.last_cstat == "656"
                    else global_cfg.blocked_message_template
                )
                try:
                    blocked_reason = template.format(
                        time=dh_str,
                        minutes=minutes_remaining,
                        interval=global_cfg.cooldown_interval_minutes,
                    )
                except Exception:
                    blocked_reason = f"Consulta bloqueada temporariamente. Próxima requisição permitida após às {dh_str} (faltam {minutes_remaining} min)."

            # Regra 2: Intervalo mínimo configurável desde a última sincronização bem-sucedida na SEFAZ
            elif state.last_sync_at and (now - state.last_sync_at) < timedelta(minutes=global_cfg.cooldown_interval_minutes):
                if state.last_cstat in ("137", "138") and (state.ult_nsu == state.max_nsu or state.last_cstat == "137"):
                    is_blocked = True
                    allowed_time = state.last_sync_at + timedelta(minutes=global_cfg.cooldown_interval_minutes)
                    minutes_remaining = max(1, int((allowed_time - now).total_seconds() // 60))
                    dh_str = allowed_time.strftime("%H:%M:%S (%d/%m/%Y)")
                    try:
                        blocked_reason = global_cfg.blocked_message_template.format(
                            time=dh_str,
                            minutes=minutes_remaining,
                            interval=global_cfg.cooldown_interval_minutes,
                        )
                    except Exception:
                        blocked_reason = f"A última consulta foi realizada recentemente. Para proteger seu CNPJ contra penalidades da SEFAZ, aguarde até {dh_str} (faltam {minutes_remaining} min)."

        if request.method == "POST":
            if is_blocked:
                return Response(
                    {
                        "error": blocked_reason,
                        "blocked": True,
                        "cstat": state.last_cstat,
                        "reason": state.last_reason,
                        "ult_nsu": state.ult_nsu,
                        "max_nsu": state.max_nsu,
                        "last_sync_at": state.last_sync_at,
                        "next_allowed_at": state.next_allowed_at,
                        "minutes_remaining": minutes_remaining,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                _perform_sync(state)
                state.refresh_from_db()
            except Exception as e:
                return Response(
                    {"error": f"Falha na comunicação com a SEFAZ: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Recalcular bloqueio após o sync
            now = timezone.now()
            if state.next_allowed_at and state.next_allowed_at > now:
                is_blocked = True
                minutes_remaining = max(1, int((state.next_allowed_at - now).total_seconds() // 60))
                blocked_reason = f"Próxima sincronização permitida após às {state.next_allowed_at.strftime('%H:%M:%S (%d/%m/%Y)')}."

        return Response({
            "status": "ok",
            "has_certificate": True,
            "restaurant_id": str(restaurant_id),
            "restaurant_name": restaurant_name,
            "cstat": state.last_cstat,
            "reason": state.last_reason,
            "ult_nsu": state.ult_nsu,
            "max_nsu": state.max_nsu,
            "last_sync_at": state.last_sync_at,
            "next_allowed_at": state.next_allowed_at,
            "is_blocked": is_blocked,
            "blocked_reason": blocked_reason,
            "minutes_remaining": minutes_remaining,
            "sync_interval_hours": 3,
            "invoices_count": InboundNFe.objects.filter(account=request.account, restaurant_id=restaurant_id).count(),
        })

    @action(detail=False, methods=["post"], url_path="set-nsu")
    def set_nsu(self, request, *args, **kwargs):
        """Atualiza manualmente o NSU de consulta e limpa bloqueios de cooldown."""
        import re
        from apps.invoices.models import FiscalConfig
        from apps.inbound_nfe.models import DFeSyncState

        nsu_raw = request.data.get("ult_nsu") or request.data.get("nsu")
        if nsu_raw is None:
            return Response({"error": "Campo 'ult_nsu' é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)

        clean_nsu = str(nsu_raw).strip().zfill(15)

        restaurant_id = (
            request.data.get("restaurant")
            or request.query_params.get("restaurant")
            or request.headers.get("X-Restaurant-ID")
            or getattr(getattr(request.user, "profile", None), "restaurant_id", None)
        )

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

        state = None
        if config and config.restaurant:
            state = DFeSyncState.objects.filter(
                account=request.account,
                restaurant=config.restaurant
            ).first()

        if not state:
            state, _ = DFeSyncState.objects.get_or_create(
                account=request.account,
                branch=config.branch if config else None,
                restaurant=config.restaurant if config else None,
                defaults={
                    'cnpj': cnpj,
                    'ult_nsu': clean_nsu,
                }
            )
        state.ult_nsu = clean_nsu
        state.next_allowed_at = None
        state.sync_error_count = 0
        state.save(update_fields=['ult_nsu', 'next_allowed_at', 'sync_error_count'])

    @action(detail=False, methods=["post"], url_path="fetch-nsu")
    def fetch_nsu(self, request, *args, **kwargs):
        """
        Consulta pontual de um NSU específico na SEFAZ via consNSU e processa a NF-e.
        """
        from apps.inbound_nfe.tasks import fetch_and_process_specific_nsu
        from apps.restaurants.models import Restaurant
        from apps.invoices.models import FiscalConfig

        nsu_raw = request.data.get("nsu") or request.query_params.get("nsu")
        if not nsu_raw:
            return Response(
                {"error": "Informe o parâmetro 'nsu' para consulta pontual."},
                status=status.HTTP_400_BAD_REQUEST
            )

        restaurant_id = (
            request.data.get("restaurant")
            or request.query_params.get("restaurant")
            or request.headers.get("X-Restaurant-ID")
            or request.headers.get("x-restaurant-id")
            or request.META.get("HTTP_X_RESTAURANT_ID")
            or getattr(getattr(request.user, "profile", None), "restaurant_id", None)
        )

        restaurant = None
        if restaurant_id:
            restaurant = Restaurant.all_objects.filter(id=restaurant_id, account=request.account).first()

        if not restaurant:
            # Pegar primeiro restaurante com certificado ativo
            configs = FiscalConfig.all_objects.filter(account=request.account, certificate_file__isnull=False)
            first_cfg = configs.first()
            if first_cfg and first_cfg.restaurant:
                restaurant = first_cfg.restaurant

        if not restaurant:
            return Response(
                {"error": "Selecione um restaurante com Certificado Digital A1 configurado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = fetch_and_process_specific_nsu(
                account=request.account,
                restaurant=restaurant,
                nsu=str(nsu_raw).strip()
            )
            return Response({
                "message": f"Consulta consNSU({nsu_raw}) realizada com sucesso.",
                "restaurant_name": restaurant.trade_name,
                "summary": result,
            })
        except Exception as e:
            return Response(
                {"error": f"Erro na consulta consNSU: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=["post"], url_path="upload-xml", parser_classes=[MultiPartParser, FormParser, JSONParser])
    def upload_xml(self, request, *args, **kwargs):
        """
        Recebe um ou múltiplos arquivos XML de NF-e (ou pacote .zip), processa
        as notas e seus produtos, atualizando ou criando registros no banco.
        """
        from apps.inbound_nfe.services.importer import import_uploaded_files
        from apps.restaurants.models import Restaurant
        from django.core.files.uploadedfile import SimpleUploadedFile

        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files:
            # Caso o arquivo tenha sido enviado com outra chave
            for k in request.FILES:
                files.extend(request.FILES.getlist(k))

        # Suporte adicional caso venham XMLs no corpo JSON ou formato texto
        if not files and isinstance(request.data, dict):
            raw_xmls = request.data.get("xmls") or request.data.get("files") or request.data.get("xml")
            if raw_xmls:
                if isinstance(raw_xmls, str):
                    raw_xmls = [raw_xmls]
                for idx, x in enumerate(raw_xmls):
                    if isinstance(x, str) and ("<nfeProc" in x or "<NFe" in x or "<infNFe" in x):
                        files.append(SimpleUploadedFile(f"nfe_{idx}.xml", x.encode("utf-8"), content_type="application/xml"))

        if not files:
            return Response(
                {"error": "Nenhum arquivo XML ou ZIP foi enviado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        restaurant_id = (
            request.data.get("restaurant")
            or request.query_params.get("restaurant")
            or request.headers.get("X-Restaurant-ID")
            or getattr(getattr(request.user, "profile", None), "restaurant_id", None)
        )

        restaurant = None
        if restaurant_id:
            restaurant = Restaurant.all_objects.filter(id=restaurant_id, account=request.account).first()
        if not restaurant:
            restaurant = Restaurant.all_objects.filter(account=request.account).first()

        try:
            summary = import_uploaded_files(
                files=files,
                account=request.account,
                restaurant=restaurant,
            )
            return Response({
                "message": f"{summary['total_processed']} nota(s) processada(s) com sucesso.",
                "summary": summary,
            })
        except Exception as e:
            return Response(
                {"error": f"Erro ao processar arquivos XML: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"], url_path="register-science")
    def register_science_action(self, request, pk=None, *args, **kwargs):
        """
        Dispara a Ciência da Operação (evento 210210) oficial na SEFAZ e,
        se aceito, busca imediatamente o XML completo (procNFe) via consChNFe.
        """
        from apps.inbound_nfe.services.manifestation import register_science

        invoice = self.get_object()
        success, message = register_science(invoice, user=request.user)

        invoice.refresh_from_db()
        serializer = self.get_serializer(invoice)
        return Response({
            "success": success,
            "message": message,
            "invoice": serializer.data,
        }, status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="fetch-full-xml")
    def fetch_full_xml_action(self, request, pk=None, *args, **kwargs):
        """
        Consulta a SEFAZ diretamente pela chave de acesso (consChNFe) para
        obter o procNFe quando a Ciência já foi registrada.
        """
        from apps.inbound_nfe.services.manifestation import fetch_full_xml

        invoice = self.get_object()
        success = fetch_full_xml(invoice)
        invoice.refresh_from_db()
        serializer = self.get_serializer(invoice)

        if success:
            return Response({
                "success": True,
                "message": "XML completo obtido com sucesso da SEFAZ!",
                "invoice": serializer.data,
            })
        else:
            return Response({
                "success": False,
                "message": "XML completo ainda em processamento na SEFAZ. Uma tentativa em segundo plano foi enfileirada.",
                "invoice": serializer.data,
            })

    @action(detail=True, methods=["post"])
    def manifest(self, request, pk=None, *args, **kwargs):
        """Faz a manifestação do destinatário na SEFAZ."""
        import re
        from apps.invoices.models import FiscalConfig
        from apps.inbound_nfe.tasks import _resolve_uf_code

        invoice = self.get_object()
        event = request.data.get("event")
        reason = request.data.get("reason", "")

        config = FiscalConfig.objects.filter(account=invoice.account).first()
        cnpj_raw = (config.cnpj if config else "") or (config.certificate_cnpj if config else "") or getattr(invoice.account, "cnpj", "")
        cnpj = re.sub(r"\D", "", cnpj_raw or "")
        uf_raw = (config.uf if config else "") or ""
        uf_code = _resolve_uf_code(uf_raw)

        try:
            cstat, msg, dh = manifest_nfe(
                account=invoice.account,
                cnpj=cnpj,
                access_key=invoice.access_key,
                event_type=event,
                uf_code=uf_code,
                reason=reason,
            )
            
            if cstat in ("135", "136", "573"):
                invoice.manifestation_status = event
                invoice.save(update_fields=["manifestation_status"])
            
            return Response({"cstat": cstat, "message": msg})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None, *args, **kwargs):
        """Conclui a nota, gerando o movimento de estoque."""
        invoice = self.get_object()
        serializer = ReceiveInvoiceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        location_id = serializer.validated_data['location_id']
        items_data = serializer.validated_data['items']
        
        try:
            location = StockLocation.objects.get(id=location_id, account=request.account)
        except StockLocation.DoesNotExist:
            return Response({"error": "Local de estoque não encontrado."}, status=status.HTTP_404_NOT_FOUND)
            
        try:
            receipt = receive_invoice(
                invoice_id=invoice.id,
                user=request.user,
                location=location,
                items_data=items_data,
                receipt_notes=serializer.validated_data.get("notes", ""),
            )
            return Response({
                "message": "Nota recebida com sucesso.",
                "receipt_id": str(receipt.id),
                "receipt_number": receipt.receipt_number,
                "status": receipt.status,
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get", "post"], url_path="export-xml")
    def export_xml(self, request, *args, **kwargs):
        """
        Exporta as notas fiscais em seus arquivos XML originais individuais.
        - Se ids forem informados: exporta as notas selecionadas.
        - Se all=true ou ids vazio: exporta todas as notas com base nos filtros atuais.
        - Se 1 nota for exportada (e sem all): devolve o arquivo .xml direto.
        - Se múltiplas notas ou all: devolve um .zip contendo os arquivos .xml originais.
        """
        import io
        import zipfile
        from django.http import HttpResponse
        from django.utils import timezone
        from apps.inbound_nfe.models import DFeDistributionDocument

        export_all = (
            str(request.data.get("all", "")).lower() in ("true", "1")
            or str(request.query_params.get("all", "")).lower() in ("true", "1")
        )
        ids = request.data.get("ids") or request.query_params.get("ids") or []
        if isinstance(ids, str):
            ids = [i.strip() for i in ids.split(",") if i.strip()]

        qs = self.get_queryset()
        if not export_all and ids:
            qs = qs.filter(id__in=ids)
        else:
            restaurant_id = (
                request.data.get("restaurant")
                or request.query_params.get("restaurant")
                or request.headers.get("X-Restaurant-ID")
            )
            if restaurant_id:
                qs = qs.filter(restaurant_id=restaurant_id)

            issue_after = request.data.get("issue_date_after") or request.query_params.get("issue_date_after")
            if issue_after:
                qs = qs.filter(issue_date__gte=issue_after)

            issue_before = request.data.get("issue_date_before") or request.query_params.get("issue_date_before")
            if issue_before:
                qs = qs.filter(issue_date__lte=issue_before)

            search = request.data.get("search") or request.query_params.get("search")
            if search:
                from django.db.models import Q
                qs = qs.filter(
                    Q(number__icontains=search)
                    | Q(access_key__icontains=search)
                    | Q(supplier_name__icontains=search)
                    | Q(supplier_cnpj__icontains=search)
                )

        notes = list(qs.order_by("-issue_date", "-created_at"))
        if not notes:
            return Response(
                {"error": "Nenhuma nota fiscal encontrada para exportação."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Se for apenas 1 nota selecionada (e não export_all)
        if len(notes) == 1 and not export_all:
            note = notes[0]
            xml_content = note.full_xml or note.summary_xml
            if not xml_content and note.access_key:
                doc = DFeDistributionDocument.all_objects.filter(account=request.account, access_key=note.access_key).first()
                if doc:
                    xml_content = doc.xml
            if not xml_content:
                return Response({"error": "XML não localizado para esta nota fiscal."}, status=status.HTTP_404_NOT_FOUND)

            filename = f"{note.access_key or f'NFe_{note.number}_{note.series}'}.xml"
            response = HttpResponse(xml_content.encode("utf-8"), content_type="application/xml; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            response["Access-Control-Expose-Headers"] = "Content-Disposition"
            return response

        # Múltiplas notas ou "Exportar Tudo" -> gera arquivo ZIP com os XMLs originais
        zip_buffer = io.BytesIO()
        exported_count = 0
        used_filenames = set()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for note in notes:
                xml_content = note.full_xml or note.summary_xml
                if not xml_content and note.access_key:
                    doc = DFeDistributionDocument.all_objects.filter(account=request.account, access_key=note.access_key).first()
                    if doc:
                        xml_content = doc.xml

                if xml_content:
                    base_name = note.access_key or f"NFe_{note.number}_{note.series}"
                    filename = f"{base_name}.xml"
                    idx = 1
                    while filename in used_filenames:
                        filename = f"{base_name}_{idx}.xml"
                        idx += 1
                    used_filenames.add(filename)

                    zf.writestr(filename, xml_content.encode("utf-8"))
                    exported_count += 1

        if exported_count == 0:
            return Response({"error": "Nenhum arquivo XML disponível para as notas selecionadas."}, status=status.HTTP_404_NOT_FOUND)

        now_str = timezone.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"nfe_export_{now_str}.zip"

        response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
        response["Access-Control-Expose-Headers"] = "Content-Disposition"
        return response


class InboundNFeItemViewSet(BaseTenantViewSet):
    queryset = InboundNFeItem.objects.all()
    # Serializer padrão para as leituras basicas seria o InboundNFeItemSerializer, mas aqui 
    # apenas expomos a action de mapeamento para o frontend.
    
    @action(detail=True, methods=["post"])
    def map(self, request, pk=None, *args, **kwargs):
        """Faz o DE/PARA manual do item da nota para um Product ou Ingredient interno."""
        item = self.get_object()
        serializer = InboundNFeItemMapRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ingredient_id = serializer.validated_data.get("ingredient_id")
        product_id = serializer.validated_data.get("product_id")
        conversion_factor = serializer.validated_data.get("conversion_factor", Decimal("1"))
        save_mapping = serializer.validated_data.get("save_supplier_mapping", True)

        try:
            ingredient = (
                Ingredient.objects.filter(id=ingredient_id, account=request.account).first()
                if ingredient_id
                else None
            )
            product = (
                Product.objects.filter(id=product_id, account=request.account).first()
                if product_id
                else None
            )

            if not product and not ingredient:
                return Response(
                    {"error": "Informe pelo menos um Produto ou Ingrediente válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            item.ingredient = ingredient
            item.product = product
            item.conversion_factor = conversion_factor
            item.save(update_fields=["ingredient", "product", "conversion_factor"])

            # Checar se a NF mudou status para pronta para recebimento
            unmapped_exists = item.invoice.items.filter(product__isnull=True, ingredient__isnull=True).exists()
            if not unmapped_exists:
                item.invoice.status = InboundNFe.STATUS_PENDING_RECEIPT
                item.invoice.save(update_fields=["status"])

            if save_mapping and item.invoice.supplier_cnpj:
                mapping_defaults = {
                    "ingredient": ingredient,
                    "product": product,
                    "supplier_description": item.description,
                    "conversion_factor": conversion_factor,
                    "confirmed_by_user": True,
                }
                if item.supplier_code:
                    SupplierItemMapping.objects.update_or_create(
                        account=request.account,
                        supplier_cnpj=item.invoice.supplier_cnpj,
                        supplier_code=item.supplier_code,
                        defaults=mapping_defaults,
                    )
                if item.ean:
                    SupplierItemMapping.objects.update_or_create(
                        account=request.account,
                        supplier_cnpj=item.invoice.supplier_cnpj,
                        supplier_ean=item.ean,
                        defaults=mapping_defaults,
                    )

            return Response({"message": "Item mapeado com sucesso."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DFeDistributionDocumentViewSet(BaseTenantViewSet):
    """Visualização e consulta dos documentos brutos DF-e recebidos da SEFAZ."""
    queryset = DFeDistributionDocument.objects.all()
    serializer_class = DFeDistributionDocumentSerializer
    filterset_fields = ["document_type", "processing_status", "nsu", "access_key"]
    ordering_fields = ["nsu", "received_at", "processed_at"]
    http_method_names = ["get", "head", "options"]

