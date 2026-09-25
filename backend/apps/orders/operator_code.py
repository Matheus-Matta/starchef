"""O código de quem lançou — atribuição, não autenticação.

O CASO CONCRETO: um totem no salão, com o app aberto e uma sessão só. Quem lança
o item não é o usuário logado — são vários garçons usando o mesmo aparelho. Sem
mais nada, todo lançamento do dia fica no nome do mesmo login, e a pergunta "quem
anotou isso?" deixa de ter resposta.

O código resolve isso e NADA MAIS. Ele não é conferido contra cadastro nenhum, de
propósito: a política é interna do restaurante (matrícula, número do crachá, o
que eles decidirem), e exigir cadastro transformaria uma medida de rastro em mais
um cadastro para manter. O que ele dá é ATRIBUIÇÃO — a linha do item passa a
dizer quem a registrou.

O que ele NÃO dá, e não deve ser confundido com isso:

- **não autentica.** Qualquer número passa, e quem sabe o do colega pode usá-lo.
  Permissão continua vindo do usuário logado.
- **não autoriza.** Nenhuma regra de cancelamento, desconto ou caixa olha este
  código.

Só dígitos. Letra e acento em código digitado às pressas num totem viram dois
registros para a mesma pessoa ("Joao" e "joão"), e o relatório mostra os dois.
"""

from django.core.exceptions import ValidationError

from apps.core.metafields import normalizar

# A chave canônica. Uma constante porque três lugares gravam nela (pedido,
# comanda, item) e um relatório a lê: escrever a string à mão em cada um deles
# faria o dia do primeiro erro de digitação ser o dia em que o rastro sumiu.
CHAVE = "operator_code"

MAX_DIGITOS = 20


def codigo_de(metafields):
    """O código gravado, ou string vazia."""
    if not isinstance(metafields, dict):
        return ""
    return str(metafields.get(CHAVE) or "").strip()


def normalizar_codigo(bruto, *, campo="metafields"):
    """Só dígitos, sem separador, com tamanho de gente.

    Devolve string vazia para ausência — quem exige é `exigir`, e separar as duas
    coisas deixa o campo opcional onde o restaurante não pediu."""
    texto = str(bruto or "").strip()
    if not texto:
        return ""
    if not texto.isdigit():
        raise ValidationError(
            {campo: "O código do operador aceita apenas números."}
        )
    if len(texto) > MAX_DIGITOS:
        raise ValidationError(
            {campo: f"O código do operador passa de {MAX_DIGITOS} dígitos."}
        )
    return texto


def preparar(metafields, *, campo="metafields"):
    """Normaliza o dicionário inteiro e, dentro dele, o código."""
    limpo = normalizar(metafields, campo=campo)
    if CHAVE in limpo:
        codigo = normalizar_codigo(limpo[CHAVE], campo=campo)
        if codigo:
            limpo[CHAVE] = codigo
        else:
            # Chave presente e vazia é ruído: ela faria o relatório contar um
            # lançamento "com código" que não tem código nenhum.
            limpo.pop(CHAVE)
    return limpo


def exige_codigo(restaurant):
    """Este restaurante pede o código antes do lançamento?"""
    return bool(getattr(restaurant, "require_operator_code", False))


def exigir(restaurant, metafields, *, campo="metafields", acao="lançar"):
    """Prepara os campos e, quando o restaurante exige, cobra o código.

    Devolve o dicionário pronto para gravar. Levanta `ValidationError` com a
    mensagem que o app mostra ao garçom — ela cita a AÇÃO porque "informe o
    código" sozinho, numa tela que faz três coisas, não diz o que foi barrado.
    """
    limpo = preparar(metafields, campo=campo)
    if exige_codigo(restaurant) and not codigo_de(limpo):
        raise ValidationError(
            {
                campo: (
                    f"Este restaurante pede o código do operador para {acao}. "
                    "Informe o código antes de continuar."
                )
            }
        )
    return limpo
