"""Le o log JSON do Django e transforma cada 500 em uma CAUSA RAIZ.

O relatorio de carga sabe que a rota devolveu 500; so o log do servidor sabe
*por que*. Cruzar os dois e o que transforma "3082 erros" em "quatro linhas de
codigo para corrigir".
"""
import json
import re

QUADRO = re.compile(r'File "(?:[A-Za-z]:)?[\\/](?:.*?)backend[\\/](.+?)", line (\d+), in (\w+)')
# A ultima linha do traceback, na coluna 0: `modulo.Classe: mensagem`. Casar so
# nomes terminados em "Error" perderia `decimal.InvalidOperation` e
# `Model.DoesNotExist` — justamente duas das causas mais frequentes aqui.
EXCECAO = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)(?::[ 	]*(.*))?$", re.M)
NAO_E_EXCECAO = ("Traceback", "During", "The", "SystemExit")
MARCA = "Unhandled API error"


class Falha:
    """Uma causa raiz: excecao + ultimo quadro no codigo do projeto."""

    def __init__(self, excecao, mensagem, arquivo, linha, funcao):
        self.excecao = excecao
        self.mensagem = mensagem
        self.arquivo = arquivo.replace("\\", "/")
        self.linha = linha
        self.funcao = funcao
        self.ocorrencias = 0
        self.rotas = {}

    @property
    def chave(self):
        return (self.excecao, self.arquivo, self.linha)

    @property
    def local(self):
        return f"backend/{self.arquivo}:{self.linha} ({self.funcao})"

    def registrar(self, rota):
        self.ocorrencias += 1
        if rota:
            self.rotas[rota] = self.rotas.get(rota, 0) + 1

    def rotas_ordenadas(self, limite=3):
        return sorted(self.rotas.items(), key=lambda item: -item[1])[:limite]


def _ultimo_quadro_do_projeto(traceback_texto):
    quadros = QUADRO.findall(traceback_texto)
    return quadros[-1] if quadros else None


def _excecao_final(traceback_texto):
    achadas = [
        (nome, mensagem) for nome, mensagem in EXCECAO.findall(traceback_texto)
        if not nome.startswith(NAO_E_EXCECAO) and ("." in nome or nome[0].isupper())
    ]
    return achadas[-1] if achadas else ("Desconhecida", "")


def ler(caminho, desde_linha=0):
    """Devolve as falhas agrupadas por causa raiz, da mais frequente para a menos."""
    falhas = {}
    try:
        with open(caminho, encoding="utf-8", errors="replace") as arquivo:
            linhas = arquivo.readlines()
    except OSError:
        return []
    for linha in linhas[desde_linha:]:
        if MARCA not in linha:
            continue
        try:
            registro = json.loads(linha)
        except ValueError:
            continue
        traceback_texto = registro.get("exc_info") or ""
        quadro = _ultimo_quadro_do_projeto(traceback_texto)
        if quadro is None:
            continue
        excecao, mensagem = _excecao_final(traceback_texto)
        falha = Falha(excecao, mensagem, quadro[0], quadro[1], quadro[2])
        existente = falhas.get(falha.chave)
        if existente is None:
            existente = falhas[falha.chave] = falha
        rota = f"{registro.get('method', '?')} {registro.get('path', '?')}"
        existente.registrar(rota if "?" not in rota else "")
    return sorted(falhas.values(), key=lambda f: -f.ocorrencias)


def contar_linhas(caminho):
    """Marca onde o log esta agora, para a proxima leitura pegar so o novo."""
    try:
        with open(caminho, encoding="utf-8", errors="replace") as arquivo:
            return sum(1 for _ in arquivo)
    except OSError:
        return 0


#: Correcao sugerida por classe de excecao. O texto vai direto para o plano.
RECEITAS = {
    "KeyError": (
        "campo obrigatorio lido com `request.data[...]` sem checagem",
        "trocar por `.get()` + `ValidationError` — o handler de `apps/core/exceptions.py` "
        "converte em 400 com mensagem",
    ),
    "DoesNotExist": (
        "`objects.get(...)` com identificador que o usuario mandou",
        "usar `.filter(...).first()` e devolver 400/404 explicando qual referencia nao existe",
    ),
    "InvalidOperation": (
        "numero vindo do corpo entrou no Decimal sem limite: ou e texto livre "
        "(`Decimal(str('dez reais'))`), ou nao cabe no `max_digits` do campo ao gravar",
        "validar antes: try/except InvalidOperation devolvendo 400, e `MaxValueValidator` "
        "coerente com `max_digits`/`decimal_places` do model",
    ),
    "OverflowError": (
        "inteiro grande demais para a coluna (o serializer nao limita o valor)",
        "declarar `max_value` no serializer ou `MaxValueValidator` no campo — hoje o numero "
        "atravessa a validacao e estoura no driver do banco",
    ),
    "OperationalError": (
        "contencao de escrita no banco",
        "nao e bug de codigo: SQLite serializa escrita. Confira WAL/`transaction_mode` "
        "e repita contra Postgres",
    ),
    "IntegrityError": (
        "violacao de unicidade/FK escapando do handler",
        "ja vira 409 em `api_exception_handler`; se chegou como 500, a excecao foi capturada "
        "e relancada fora do ciclo do DRF",
    ),
}


def receita(excecao):
    for chave, valor in RECEITAS.items():
        if excecao.endswith(chave):
            return valor
    return ("excecao nao tratada na view", "capturar e converter em resposta 4xx com mensagem")
