"""Preservação dos horários de origem ao inserir dados sincronizados."""


def inserir_preservando_horarios_de_origem(instancia, valores):
    """Insere a linha e restaura timestamps que Django recalcula no INSERT.

    `auto_now_add` troca o horário recebido pelo horário atual; `auto_now`
    também recalcula `updated_at`. Sem restaurar esses campos, um pedido criado
    na nuvem aparece na loja como se tivesse sido aberto naquele instante.
    """
    horarios = {
        campo.attname: valores[campo.attname]
        for campo in instancia._meta.concrete_fields
        if (getattr(campo, "auto_now_add", False) or getattr(campo, "auto_now", False))
        and campo.attname in valores
    }

    instancia.save(force_insert=True)
    _restaurar(instancia, horarios)


def atualizar_preservando_horarios_de_origem(instancia, valores):
    """O mesmo para a ATUALIZAÇÃO — e aqui o horário é a versão do registro.

    `auto_now` dava à linha aplicada o `updated_at` de "agora", e a versão é o
    `updated_at` em microssegundos. A edição que o outro lado fez às 10:00:03,
    chegando depois de a de 10:00:00 ter sido aplicada às 10:00:05, parecia
    mais VELHA que a linha local e era descartada — e uma versão de fato velha
    passava por nova e sobrescrevia a certa.
    """
    horarios = _horarios(instancia, valores, so_auto_now=True)
    instancia.save()
    _restaurar(instancia, horarios)


def _horarios(instancia, valores, *, so_auto_now):
    return {
        campo.attname: valores[campo.attname]
        for campo in instancia._meta.concrete_fields
        if (getattr(campo, "auto_now", False)
            or (not so_auto_now and getattr(campo, "auto_now_add", False)))
        and campo.attname in valores
        and valores[campo.attname] is not None
    }


def _restaurar(instancia, horarios):
    if not horarios:
        return
    type(instancia)._base_manager.using(instancia._state.db).filter(
        pk=instancia.pk
    ).update(**horarios)
    for nome, valor in horarios.items():
        setattr(instancia, nome, valor)
