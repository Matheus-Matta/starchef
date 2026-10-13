# Carregado por instalar.sh: põe a ACBrLib (lib + Schemas da NF-e) em acbr/libs.
#
# O pacote é o da compilação do Projeto ACBr (docs/FISCAL_ACBRLIB.md). A lib
# é conferida pelo SHA-256 ANTES de ir para acbr/libs: uma página de erro, um
# download pela metade ou uma lib trocada viram aviso, nunca uma lib carregada
# pelo emissor que assina as notas da empresa.
#
# Nunca derruba a instalação: sem a lib a loja sobe igual, e o caixa lê
# "ACBrLib não instalada" com a providência quando o provedor for ACBrLib.
default ACBRLIB_PACOTE_URL https://www.mediafire.com/file/hd3t2w7uqc2r6b3/acbr-fiscal-linux-x64.tar.gz/file
default ACBRLIB_SO_SHA256 deec61a921b830516ad3d7f5833aee7cb69603391eb497e649296ecc5522b3f0
mkdir -p acbr/libs

sha256_de() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

# O link direto do MediaFire muda a cada visita: ele é lido da página do arquivo.
link_direto() {
  case "$1" in
    *mediafire.com/file/*)
      curl -fsSL -A 'Mozilla/5.0' "$1" 2>/dev/null |
        grep -oE 'https://download[0-9]*\.mediafire\.com/[^"'"'"' ]+' | head -n 1 ;;
    *) printf '%s\n' "$1" ;;
  esac
}

acbrlib_instalada() {
  [ -f acbr/libs/libacbrnfe64.so ] && [ -d acbr/libs/Schemas ] &&
    [ "$(sha256_de acbr/libs/libacbrnfe64.so)" = "$(ler ACBRLIB_SO_SHA256)" ]
}

instalar_acbrlib() {
  url=$(ler ACBRLIB_PACOTE_URL)
  [ -n "$url" ] || { echo "ACBrLib: sem ACBRLIB_PACOTE_URL; copie a lib para acbr/libs à mão."; return 0; }
  tmp=$(mktemp -d)
  echo "ACBrLib: baixando o pacote..."
  direto=$(link_direto "$url" || true)
  if [ -z "$direto" ] || ! curl -fsSL -A 'Mozilla/5.0' -o "$tmp/pacote.tar.gz" "$direto" ||
     ! tar -xzf "$tmp/pacote.tar.gz" -C "$tmp" 2>/dev/null; then
    echo "ACBrLib: não consegui baixar o pacote de $url. A loja sobe sem emissor; copie a lib para acbr/libs depois." >&2
    rm -rf "$tmp"; return 0
  fi
  so=$(find "$tmp" -name libacbrnfe64.so | head -n 1)
  if [ -z "$so" ] || [ "$(sha256_de "$so")" != "$(ler ACBRLIB_SO_SHA256)" ]; then
    echo "ACBrLib: a lib baixada não confere com ACBRLIB_SO_SHA256. Nada foi instalado." >&2
    rm -rf "$tmp"; return 0
  fi
  # O ACBrLib.ini do comunicador lê os .xsd direto em /app/libs/Schemas.
  origem=$(dirname "$so")/Schemas/NFe
  [ -d "$origem" ] || origem=$(dirname "$so")/Schemas
  mkdir -p acbr/libs/Schemas
  if ! cp "$so" acbr/libs/libacbrnfe64.so || ! cp "$origem"/*.xsd acbr/libs/Schemas/; then
    echo "ACBrLib: o pacote não tem os Schemas esperados. Copie a lib para acbr/libs à mão." >&2
    rm -rf "$tmp"; return 0
  fi
  # O container lê como root, mas o umask 077 do instalador deixaria só o dono.
  chmod 755 acbr/libs acbr/libs/Schemas
  chmod 644 acbr/libs/libacbrnfe64.so acbr/libs/Schemas/*.xsd
  rm -rf "$tmp"
  echo "ACBrLib instalada em acbr/libs ($(ls acbr/libs/Schemas | wc -l | tr -d ' ') Schemas)."
}

acbrlib_instalada || instalar_acbrlib
