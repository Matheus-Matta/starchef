"""Campos adicionais livres, com porta estreita.

`metafields` existe para o restaurante guardar o que o schema não previu — hoje o
código do garçom num totem, amanhã outra coisa — sem que cada necessidade nova
vire uma coluna. É deliberadamente livre no CONTEÚDO e fechado no FORMATO.

O FORMATO É FECHADO PORQUE O CLIENTE ESCREVE NELE. Um `JSONField` que aceita
qualquer coisa vinda de um app é um lugar para gravar megabytes, estrutura
aninhada que ninguém consegue consultar depois, e chave com espaço que quebra
todo relatório que tentar agrupar. O limite não é desconfiança do operador: é o
que mantém o campo utilizável seis meses depois.

O que passa: dicionário raso, chaves em `a-z0-9_`, valores escalares curtos.
"""

from django.core.exceptions import ValidationError

MAX_CHAVES = 20
MAX_TAMANHO_DA_CHAVE = 40
MAX_TAMANHO_DO_VALOR = 120

# Chaves são normalizadas para caixa baixa: "Codigo" e "codigo" gravados no mesmo
# campo seriam dois registros para a mesma coisa, e o relatório mostraria os dois.
_CHAVE_VALIDA = "abcdefghijklmnopqrstuvwxyz0123456789_"

ESCALARES = (str, int, float, bool)


def normalizar(bruto, *, campo="metafields"):
    """Devolve o dicionário aceito, ou levanta `ValidationError` dizendo por quê.

    `None` e `{}` viram `{}`: ausência não é erro. O campo é opcional em todo
    lugar onde existe.
    """
    if bruto in (None, ""):
        return {}
    if not isinstance(bruto, dict):
        raise ValidationError({campo: "Informe os campos adicionais como um objeto."})
    if len(bruto) > MAX_CHAVES:
        raise ValidationError(
            {campo: f"No máximo {MAX_CHAVES} campos adicionais por registro."}
        )
    limpo = {}
    for chave, valor in bruto.items():
        limpo[_chave(chave, campo)] = _valor(chave, valor, campo)
    return limpo


def _chave(chave, campo):
    texto = str(chave).strip().lower()
    if not texto:
        raise ValidationError({campo: "Campo adicional sem nome."})
    if len(texto) > MAX_TAMANHO_DA_CHAVE:
        raise ValidationError(
            {campo: f'O nome "{texto[:20]}…" passa de {MAX_TAMANHO_DA_CHAVE} caracteres.'}
        )
    if any(letra not in _CHAVE_VALIDA for letra in texto):
        raise ValidationError(
            {
                campo: (
                    f'O nome "{texto}" só pode ter letras, números e sublinhado. '
                    "Espaço e acento quebram qualquer agrupamento depois."
                )
            }
        )
    return texto


def _valor(chave, valor, campo):
    """Escalar, e sempre guardado como TEXTO.

    Texto por decisão: o mesmo campo recebe "12" de um cliente e `12` de outro, e
    guardar os dois como vieram faria a consulta por igualdade achar metade dos
    registros. Booleano vira "true"/"false" pelo mesmo motivo.
    """
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if not isinstance(valor, ESCALARES):
        raise ValidationError(
            {
                campo: (
                    f'O campo "{chave}" precisa ser texto ou número. '
                    "Lista e objeto aninhado não entram aqui."
                )
            }
        )
    texto = str(valor).strip()
    if len(texto) > MAX_TAMANHO_DO_VALOR:
        raise ValidationError(
            {campo: f'O valor de "{chave}" passa de {MAX_TAMANHO_DO_VALOR} caracteres.'}
        )
    return texto


def herdar(destino, origem):
    """Copia de `origem` o que falta em `destino`, sem sobrescrever nada.

    É como o pedido herda os campos da comanda: o que o caixa registrou no pedido
    vale mais do que o que estava na comanda — ele é mais recente e mais
    específico. Sobrescrever apagaria o registro de quem fechou a conta em favor
    do de quem abriu o cartão.
    """
    herdado = dict(normalizar(origem))
    herdado.update(normalizar(destino))
    return herdado
