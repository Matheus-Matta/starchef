#!/bin/sh
# O que TODO processo desta imagem faz antes de começar.
#
# Existe por causa de um defeito que custou um dia inteiro de diagnóstico: a
# nuvem subiu com `orders_commandbatch` e `orders_commanditem` sem trigger de
# captura, porque o `docker-compose` dela — diferente do da loja — não rodava
# `sync_install_triggers` no boot. O domínio da comanda escreve por
# `QuerySet.update()` em seis lugares, e `update()` não dispara signal: a
# trigger era o ÚNICO caminho para aquilo virar evento.
#
# O resultado foi silencioso. Comanda cobrada continuava pendente do outro
# lado, cartão nunca liberava, e nada no log dizia por quê.
#
# Deixar isso no `command` de cada compose é confiar que toda instalação — de
# toda loja, de todo cliente — lembrou de escrever a mesma linha. Aqui, quem
# usa a imagem recebe a rede de segurança sem saber que ela existe.
set -e

# `--if-needed` para o caso normal não custar nada: ele consulta o catálogo do
# Postgres e sai sem DDL quando não falta nada. Importa porque quatro
# containers (backend, worker, beat, sync_worker) sobem juntos com esta mesma
# imagem — recriar 55 triggers em cada um pegaria ACCESS EXCLUSIVE em todas as
# tabelas sincronizadas e serializaria o arranque por trabalho já feito.
#
# `|| true` porque a rede de segurança NUNCA pode impedir a loja de vender: se
# o banco ainda não subiu, se é SQLite, se a sincronização está desligada, o
# processo segue e o próximo boot tenta de novo. O comando já diz em voz alta
# o que encontrou.
python manage.py sync_install_triggers --if-needed || true

exec "$@"
