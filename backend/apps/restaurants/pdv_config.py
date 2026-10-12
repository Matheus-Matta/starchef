"""`GET /pdv/config/` — o que o PDV e o app do garçom pegam na nuvem ao logar.

Hoje é o IP do server local do restaurante: o app entra na nuvem (fixa em
api.starchef.com.br), pergunta aqui onde fica a loja e passa a usá-la. Antes o
endereço era digitado em cada terminal e em cada celular, e mudar o IP do
servidor era refazer isso aparelho por aparelho.
"""
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def url_da_api(valor):
    """O IP como foi digitado → o endereço da API que o app usa.

    "192.168.0.10" e "http://192.168.0.10:8000/api/v1/" chegam do mesmo jeito
    ao app: com esquema e com o caminho da API. Vazio continua vazio.
    """
    texto = (valor or "").strip().rstrip("/")
    if not texto:
        return ""
    if "://" not in texto:
        texto = f"http://{texto}"
    esquema, resto = texto.split("://", 1)
    if "/" not in resto:
        texto = f"{texto}/api/v1"
    return texto


class PdvConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurante = getattr(getattr(request.user, "profile", None), "restaurant", None)
        return Response({
            "restaurant": str(restaurante.pk) if restaurante else None,
            "ip_server_local": url_da_api(getattr(restaurante, "ip_server_local", "")),
        })
