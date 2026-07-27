from rest_framework.pagination import CursorPagination, PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        # OFFSET sem ordenacao deterministica pode repetir/pular registros entre
        # paginas quando outra requisicao insere dados no mesmo intervalo.
        if hasattr(queryset, "ordered") and not queryset.ordered:
            queryset = queryset.order_by("-pk")
        return super().paginate_queryset(queryset, request, view=view)


class LargeDatasetCursorPagination(CursorPagination):
    """Paginacao opt-in para endpoints append-heavy ou com tabelas muito grandes.

    O campo usado no cursor precisa ter indice e um desempate estavel. Mantemos a
    paginacao por pagina como padrao para nao quebrar o contrato do frontend atual.
    """

    page_size = 100
    ordering = ("-created_at", "-pk")
    page_size_query_param = "page_size"
    max_page_size = 250

