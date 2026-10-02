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
    if not horarios:
        return

    type(instancia)._base_manager.using(instancia._state.db).filter(
        pk=instancia.pk
    ).update(**horarios)
    for nome, valor in horarios.items():
        setattr(instancia, nome, valor)
