"""Tira a loja da faixa de ids de usuário que a nuvem usa.

## O defeito, medido

`auth.User` é a ÚNICA das 52 entidades sincronizadas cujo id não é UUID — é um
inteiro sequencial, porque é a classe embutida do Django. E `apply._inserir`
grava com `model(pk=event.entity_id)`: a loja **adota o id da nuvem**.

Ela é obrigada a adotar. Todo payload carrega FK de usuário como id cru
(`opened_by_id: 15`, `created_by_id: 15`), então se a loja numerasse por conta
própria, 145 chaves estrangeiras passariam a apontar para a pessoa errada.

O preço disso é que inserir com id explícito **não avança a sequência local**.
Medido no nó de produção: a sequência estava em `last_value=1` enquanto os
usuários vindos da nuvem ocupavam 10 a 16. O nono usuário criado na loja
receberia o id 10 — que já é de outra pessoa.

E o modo de falhar é silencioso: `_inserir` pega o `IntegrityError` e cai no
caminho de ATUALIZAR, porque "id que já existe" normalmente significa "o mesmo
registro chegando de novo". Aqui não significa: significa duas pessoas
diferentes com o mesmo número. Uma sobrescreve a outra, incluindo o hash da
senha.

## O que esta migration faz

Numa instalação LOCAL, empurra a sequência de `auth_user` para 1.000.000.000.
A partir daí, usuário criado na loja nasce nessa faixa e usuário vindo da
nuvem continua na faixa baixa — os dois nunca se encontram. O teto do `int4` é
2.147.483.647, então sobra mais de um bilhão de ids para cada lado.

Não roda na nuvem: lá a sequência é a autoridade e precisa continuar normal.
Não roda fora do PostgreSQL.

## O que ela NÃO é

É mitigação, não cura. A cura é `auth.User` ter id UUID como todo o resto do
catálogo — aí a colisão deixa de ser possível em vez de ficar improvável. Isso
exige trocar `AUTH_USER_MODEL` (que o Django documenta como muito difícil
depois das migrations iniciais), reescrever 145 colunas de chave estrangeira
de inteiro para uuid nos DOIS bancos e invalidar todo token em circulação, que
carrega `user_id` dentro. Está descrito em `docs/SINCRONIZACAO.md`.
"""
from django.db import migrations


def reservar(apps, schema_editor):
    # A lógica mora em `services/user_ids.py`, e não aqui, porque o
    # `manage.py check` precisa conferir a MESMA coisa numa instalação que já
    # estava no ar quando esta migration passou.
    from apps.synchronization.services import user_ids

    user_ids.reservar_faixa(schema_editor.connection)


def desfazer(apps, schema_editor):
    """Sem volta, de propósito.

    Baixar a sequência devolveria a loja para a faixa da nuvem — desfazer isto
    é reintroduzir o defeito. Se a migration precisar ser revertida por outro
    motivo, a sequência alta não atrapalha nada.
    """
    return


class Migration(migrations.Migration):
    dependencies = [("synchronization", "0008_ambiente_de_producao")]

    operations = [migrations.RunPython(reservar, desfazer)]
