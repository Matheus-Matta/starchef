"""As falhas de emissão, por FAMÍLIA — é a família que decide o que acontece.

Ficam fora de `providers.py` para o documento neutro (`documento.py`) e os
provedores (Focus, ACBrLib) as usarem sem importação circular. `providers.py`
continua exportando os mesmos nomes, então quem já importava de lá não muda.
A classificação em contingência ou não está em `contingency.py`.
"""


class FiscalProviderError(RuntimeError):
    """Base das falhas de emissao.

    O servico precisa saber POR QUE a emissao falhou para decidir o que fazer:
    reenviar, parar, ou consultar antes de reenviar. Antes tudo era
    ``RuntimeError`` e uma rejeicao tributaria era tratada igual a uma queda de
    rede — o que gerava retransmissao infinita de uma nota que a SEFAZ ja
    recusou em definitivo.
    """

    #: Detalhe da família para o operador (`acbrlib/cliente.py`); vazio = a frase basta.
    motivo = ""


class FiscalRejection(FiscalProviderError):
    """Documento recusado: a SEFAZ negou, ou ele nem e valido para transmitir.

    Nao existe retentativa automatica: reenviar repete a mesma recusa. So sai
    do lugar depois que alguem corrigir o cadastro ou o pedido.
    """


class FiscalConfigurationError(FiscalProviderError):
    """Certificado, token, CSC ou URL ausente/invalido.

    Nenhuma nota da empresa sai enquanto nao for corrigido, entao nao adianta
    tratar como indisponibilidade momentanea.
    """


class FiscalUnavailable(FiscalProviderError):
    """Falha tecnica temporaria: rede, timeout, 5xx, SEFAZ fora do ar.

    E a UNICA familia que justifica retentativa automatica.
    """


class FiscalNotFound(FiscalProviderError):
    """A consulta nao encontrou o documento no provedor.

    Nao e recusa: e a resposta esperada para uma nota que nunca chegou la. E a
    unica forma de resolver com seguranca uma nota em reconciliacao — se o
    provedor nao tem o documento, retransmitir nao duplica nada.
    """


class FiscalAmbiguous(FiscalProviderError):
    """A emissao pode ter acontecido, mas o resultado nao foi confirmado.

    Exige consulta pela referencia antes de qualquer reenvio — reenviar as
    cegas e o caminho para duplicar documento fiscal.
    """
