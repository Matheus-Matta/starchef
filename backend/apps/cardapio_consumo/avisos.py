"""Os avisos do cardápio de consumo no sino: o que saiu e o que faltou."""
from decimal import Decimal

from apps.cardapio_consumo.models import ExecucaoCardapio

ENTIDADE = "cardapio_consumo.ExecucaoCardapio"


def quantidade(valor, unidade):
    """3.000 kg → "3 kg"; 0.500 l → "0,5 l". Para o texto do aviso."""
    texto = f"{Decimal(str(valor)):f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return f"{texto.replace('.', ',')} {unidade}".strip()


def texto_das_faltas(faltas):
    return "; ".join(f"faltou {quantidade(f['faltou'], f['unidade'])} de {f['nome']}" for f in faltas)


def _gerentes(account_id):
    from apps.notifications.services import managers_of_account

    return list(managers_of_account(account_id))


def avisar(account, *, nivel, titulo, corpo, url="", object_id=""):
    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    destinatarios = _gerentes(account.pk)
    if destinatarios:
        notify(destinatarios, account=account, category=Notification.CATEGORY_STOCK, level=nivel, title=titulo,
               body=corpo[:1000], url=url, entity=ENTIDADE, object_id=object_id)


def avisar_execucao(execucao):
    from apps.notifications.models import Notification

    nome = execucao.cardapio.nome
    faltas = texto_das_faltas(execucao.faltas)
    url = f"/estoque-saidas/{execucao.saida_id}" if execucao.saida_id else "/cardapios-consumo"
    if execucao.situacao == ExecucaoCardapio.CONFIRMADA:
        nivel = Notification.LEVEL_WARNING if faltas else Notification.LEVEL_SUCCESS
        titulo = f"Baixa parcial: {nome}" if faltas else f"Baixa feita: {nome}"
        # Só a primeira letra: `capitalize()` baixava o resto e "Arroz" virava "arroz".
        corpo = f"Saída do estoque confirmada. {faltas[:1].upper()}{faltas[1:]}." if faltas else "Saída do estoque confirmada."
    elif execucao.situacao == ExecucaoCardapio.PARA_CONFERIR:
        nivel = Notification.LEVEL_WARNING if faltas else Notification.LEVEL_INFO
        titulo = f"Saída para conferir: {nome}"
        corpo = "A saída do dia está em rascunho: confira as quantidades e confirme."
        corpo += f" Sem saldo: {faltas}." if faltas else ""
    elif execucao.situacao == ExecucaoCardapio.SEM_SALDO:
        nivel, titulo = Notification.LEVEL_WARNING, f"Sem saldo para baixar: {nome}"
        corpo = f"Nada saiu do estoque: {faltas}."
    else:
        nivel, titulo = Notification.LEVEL_ERROR, f"Baixa não executada: {nome}"
        corpo = execucao.mensagem or "Erro inesperado."
    if execucao.situacao != ExecucaoCardapio.FALHOU and execucao.mensagem:
        corpo += f" Atenção: {execucao.mensagem}"
    avisar(execucao.account, nivel=nivel, titulo=titulo, corpo=corpo, url=url, object_id=str(execucao.pk))
