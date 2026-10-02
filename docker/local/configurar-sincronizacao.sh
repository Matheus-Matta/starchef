# Carregado por instalar.sh; coleta os dados que identificam a loja na nuvem.
gravar SYNC_ENABLED true
gravar SYNC_AUTO_ENROLL true

for chave_url in SYNC_CLOUD_API_URL SYNC_CLOUD_WSS_URL; do
  if [ -z "$(ler "$chave_url")" ]; then
    if [ "$chave_url" = SYNC_CLOUD_API_URL ]; then sugerido=https://api.starchef.com.br
    else sugerido=wss://api.starchef.com.br/ws/sync/v1/; fi
    printf '%s [%s]: ' "$chave_url" "$sugerido"
    read -r valor || valor=""
    gravar "$chave_url" "${valor:-$sugerido}"
  fi
done

nome=$(ler SYNC_NODE_NAME)
if [ -z "$nome" ] || [ "$nome" = 'Loja StarChef' ] || [ "$nome" = 'Loja Centro' ]; then
  printf 'Nome da loja (como aparecerá na nuvem): '
  read -r nome || nome=""
  [ -n "$nome" ] || { echo 'O nome da loja é obrigatório para sincronizar.' >&2; exit 1; }
  gravar SYNC_NODE_NAME "$nome"
fi

uuid_re='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
conta=$(ler SYNC_ACCOUNT_ID)
if ! printf '%s' "$conta" | grep -Eq "$uuid_re"; then
  printf 'UUID da conta StarChef na nuvem: '
  read -r conta || conta=""
  printf '%s' "$conta" | grep -Eq "$uuid_re" || { echo 'Informe um UUID válido para a conta.' >&2; exit 1; }
  gravar SYNC_ACCOUNT_ID "$conta"
fi
loja=$(ler SYNC_STORE_ID)
if [ -z "$loja" ]; then
  printf 'UUID do restaurante/loja na nuvem (Enter para sincronizar a conta toda): '
  read -r loja || loja=""
  if [ -n "$loja" ]; then
    printf '%s' "$loja" | grep -Eq "$uuid_re" || { echo 'Informe um UUID válido ou deixe vazio.' >&2; exit 1; }
    gravar SYNC_STORE_ID "$loja"
  fi
fi

for chave in SYNC_ENROLL_USERNAME SYNC_ENROLL_PASSWORD; do
  if [ -z "$(ler "$chave")" ]; then
    printf '%s: ' "$chave"
    if [ "$chave" = SYNC_ENROLL_PASSWORD ]; then
      stty -echo
      read -r valor || valor=""
      stty echo
      echo
    else read -r valor || valor=""; fi
    [ -n "$valor" ] || { echo "$chave é obrigatório para sincronizar." >&2; exit 1; }
    gravar "$chave" "$valor"
  fi
done

ticket=$(ler SYNC_ENROLL_SECRET)
if ! printf '%s' "$ticket" | grep -Eq '^sc-[0-9a-fA-F]{40}$'; then
    echo 'No Admin da nuvem, abra Sincronização > Bilhetes de matrícula > Adicionar.'
    printf 'Selecione a conta %s, o restaurante (se aplicável) e use o nome "%s".\n' "$conta" "$nome"
    echo 'Salve, copie o código da confirmação e cole abaixo. Ele vale 30 minutos e uma matrícula.'
    printf 'Ticket de matrícula (entrada oculta): '
    stty -echo
    read -r ticket || ticket=""
    stty echo
    echo
    [ "${#ticket}" -ge 24 ] || { echo 'O ticket deve ter pelo menos 24 caracteres.' >&2; exit 1; }
    gravar SYNC_ENROLL_SECRET "$ticket"
fi
