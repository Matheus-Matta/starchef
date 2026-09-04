# Atualização e release do StarChef PDV

Este documento explica como o PDV identifica novas versões, como os pacotes de
Windows e Linux são publicados e qual é o procedimento seguro para liberar uma
atualização.

## Estado atual

O PDV possui **atualização automática transacional** no Windows e no Linux.

- ao iniciar, consulta o `latest.json` do último GitHub Release sem bloquear o
  login quando a rede ou o GitHub estiverem indisponíveis;
- compara a versão instalada com a versão publicada;
- quando existe versão nova, escolhe o ZIP portátil da plataforma, bloqueia
  temporariamente a operação e baixa o bundle completo;
- confere o tamanho e o SHA-256 antes de aceitar o download;
- descompacta em uma pasta nova, sem alterar a instalação em uso;
- inicia um processo auxiliar, encerra o PDV e todas as janelas da Balança
  Rápida que usam o mesmo executável;
- troca as pastas, inicia a versão nova e a observa por oito segundos;
- se a versão nova encerrar durante essa validação, restaura a pasta anterior e
  reinicia automaticamente o PDV antigo;
- mostra `STARCHEF vX.Y.Z` e o estado por ícone na barra lateral.

O instalador EXE continua publicado para primeira instalação e atualização
manual. A atualização automática usa o ZIP também no Windows porque a troca de
diretório permite rollback integral; executar o Inno Setup por cima da versão
existente alteraria também os metadados do instalador e impediria um rollback
realmente transacional.

> A versão `1.0.34` é o bootstrap desse mecanismo. Terminais em `1.0.33` ou
> anteriores ainda precisam receber `StarChef-PDV-Setup-1.0.34.exe` no Windows
> ou o bundle Linux `1.0.34` manualmente uma vez. A partir de um PDV que já
> contenha este atualizador, os releases superiores são aplicados sozinhos.

Esta atualização se aplica somente ao **PDV desktop**. O APK do aplicativo do
garçom possui versionamento e distribuição próprios e não está no
`latest.json` do PDV. O mesmo workflow gera o APK universal e o anexa ao
GitHub Release apenas para centralizar a distribuição; a versão do APK continua
vindo de `flutter_garcom/pubspec.yaml`.

## Visão do fluxo

```text
pubspec.yaml: 1.0.34+32
          │
          ├── tag obrigatória: v1.0.34
          │
          ▼
GitHub Actions
  ├── valida tag x pubspec do PDV
  ├── executa analyze e testes do PDV e do app do garçom
  ├── compila Windows
  │     ├── StarChef-PDV-Setup-1.0.34.exe
  │     └── StarChef-PDV-Windows-v1.0.34.zip
  ├── compila Linux
  │     └── StarChef-PDV-Linux-v1.0.34.zip
  ├── compila o APK universal do garçom
  │     └── StarChef-Garcom-v1.6.3.apk
  ├── calcula SHA-256 e tamanho dos três pacotes do PDV
  ├── gera latest.json
  └── publica tudo no GitHub Release v1.0.34
                    │
                    ▼
PDV consulta /releases/latest/download/latest.json
  ├── Windows baixa o ZIP portátil para atualização automática
  ├── Linux baixa o ZIP portátil para atualização automática
  └── EXE de Windows permanece disponível para instalação manual
```

## Fonte da versão

A fonte da versão do aplicativo é `flutter/pubspec.yaml`:

```yaml
version: 1.0.34+32
```

Os valores têm funções diferentes:

| Parte | Exemplo | Uso |
| --- | --- | --- |
| versão pública | `1.0.34` | comparação de atualização, nome dos pacotes e tag |
| build number | `32` | identifica uma compilação específica do aplicativo |
| tag Git | `v1.0.34` | inicia o release e precisa corresponder à versão pública |

Sempre incremente o build number. Se a versão anterior era `1.0.33+31`, um
novo patch pode usar `1.0.34+32`. A tag não inclui o build number.

O pipeline rejeita uma tag divergente. Por exemplo, `v1.0.35` falha se o
`pubspec.yaml` ainda contiver `version: 1.0.34+32`.

## Pacotes publicados

| Sistema | Arquivo | Papel |
| --- | --- | --- |
| Windows | `StarChef-PDV-Setup-X.Y.Z.exe` | primeira instalação ou atualização manual pelo Inno Setup |
| Windows | `StarChef-PDV-Windows-vX.Y.Z.zip` | bundle usado pelo atualizador automático transacional |
| Linux | `StarChef-PDV-Linux-vX.Y.Z.zip` | pacote principal com o bundle completo |
| Android | `StarChef-Garcom-vA.B.C.apk` | APK universal do app do garçom; não participa do `latest.json` |
| Todos | `latest.json` | manifesto consumido pelo verificador do PDV |

No Windows, prefira o instalador para a primeira instalação. O `AppId` permanece
estável e o instalador bloqueia instalação de versão igual ou inferior. Depois
disso, o próprio PDV usa o ZIP nos próximos releases.

O ZIP de Windows deve ser tratado como um bundle completo. Feche todas as
janelas do PDV e da Balança Rápida antes de trocar a pasta; não copie somente o
`.exe`, porque DLLs e plugins fazem parte da mesma versão.

No Linux, a pasta do bundle e a pasta pai precisam ser graváveis pelo usuário
que executa o PDV. Instalações protegidas por `root`, como `/opt` sem permissão
de escrita, não podem ser substituídas automaticamente; nesse caso o PDV mantém
a versão atual e registra a falha em `pdv.log`.

## Formato do `latest.json`

O manifesto usa `schema_version: 1` e separa os pacotes por plataforma:

```json
{
  "schema_version": 1,
  "version": "1.0.34",
  "tag": "v1.0.34",
  "published_at": "2026-08-26T18:00:00+00:00",
  "commit": "SHA_DO_COMMIT",
  "release_url": "https://github.com/Matheus-Matta/starchef/releases/tag/v1.0.34",
  "platforms": {
    "windows": {
      "packages": [
        {
          "kind": "installer",
          "format": "exe",
          "name": "StarChef-PDV-Setup-1.0.34.exe",
          "url": "https://github.com/Matheus-Matta/starchef/releases/download/v1.0.34/StarChef-PDV-Setup-1.0.34.exe",
          "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "size": 12345678,
          "recommended": true
        },
        {
          "kind": "portable",
          "format": "zip",
          "name": "StarChef-PDV-Windows-v1.0.34.zip",
          "url": "https://github.com/Matheus-Matta/starchef/releases/download/v1.0.34/StarChef-PDV-Windows-v1.0.34.zip",
          "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "size": 12345678,
          "recommended": false
        }
      ]
    },
    "linux": {
      "packages": [
        {
          "kind": "portable",
          "format": "zip",
          "name": "StarChef-PDV-Linux-v1.0.34.zip",
          "url": "https://github.com/Matheus-Matta/starchef/releases/download/v1.0.34/StarChef-PDV-Linux-v1.0.34.zip",
          "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
          "size": 12345678,
          "recommended": true
        }
      ]
    }
  }
}
```

O arquivo é publicado em cada release. O PDV usa a URL estável:

```text
https://github.com/Matheus-Matta/starchef/releases/latest/download/latest.json
```

O redirecionamento de `releases/latest` faz a URL acompanhar o release mais
recente sem precisar alterar ou recompilar os terminais a cada versão.

## Estados mostrados no PDV

| Estado | Significado |
| --- | --- |
| ícone neutro giratório | consulta ainda em andamento |
| ícone verde com check | versão instalada é igual ou superior à versão do manifesto |
| ícone vermelho | manifesto possui uma versão semântica superior |
| ícone neutro com interrogação | falha de rede, HTTP, JSON, versão ou pacote da plataforma |

A versão instalada aparece ao lado do produto, por exemplo
`STARCHEF v1.0.34`, sem exibir o build number. Os detalhes ficam no tooltip do
ícone. O clique no ícone repete a consulta. O timeout e qualquer erro ficam
isolados do fluxo de vendas.

## Configuração do GitHub

O workflow está em `.github/workflows/flutter.yml`.

Configure no repositório:

| Tipo | Nome | Obrigatório | Uso |
| --- | --- | --- | --- |
| Variable | `PDV_API_BASE_URL` | sim | URL da API incorporada aos builds |
| Secret | `PDV_SENTRY_DSN` | não | telemetria do PDV |
| Variable | `PDV_UPDATE_MANIFEST_URL` | não | substitui a URL padrão do GitHub |
| Secret | `GARCOM_KEYSTORE_BASE64` | não | JKS do app do garçom codificado em Base64 |
| Secret | `GARCOM_KEYSTORE_PASSWORD` | não | senha do keystore Android |
| Secret | `GARCOM_KEY_ALIAS` | não | alias da chave de assinatura |
| Secret | `GARCOM_KEY_PASSWORD` | não | senha da chave de assinatura |

Sem `PDV_UPDATE_MANIFEST_URL`, o Actions calcula automaticamente:

```text
https://github.com/<owner>/<repository>/releases/latest/download/latest.json
```

O override é útil se o manifesto passar a ser entregue por domínio próprio ou
CDN. Ele é incorporado no binário por `--dart-define`; não é um segredo.

Os quatro Secrets `GARCOM_*` são opcionais, em tag ou em `workflow_dispatch`.
Sem eles, o job publica o APK assinado com a chave de debug do Flutter e o
Actions mostra um aviso explícito — o app do garçom ainda não depende de
atualização in-place, então essa assinatura variável não bloqueia o release do
PDV. Configure os quatro Secrets somente quando o APK precisar reinstalar por
cima de uma versão já instalada (mesma assinatura entre builds). Se apenas
parte dos quatro estiver definida, o job falha por configuração incompleta.

Para cadastrar o JKS local no GitHub sem versioná-lo, gere o Base64 no
PowerShell e copie somente a saída para o Secret `GARCOM_KEYSTORE_BASE64`:

```powershell
[Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("flutter_garcom/android/starchef-garcom-release.jks")
)
```

Cadastre os quatro valores em **Settings → Secrets and variables → Actions →
Secrets**. Nunca adicione `key.properties`, o JKS ou suas senhas ao Git.

## Por que aparecem vários processos no Actions

Abrir um Pull Request e enviar uma tag são dois eventos independentes. Se os
dois acontecerem próximos um do outro, é normal aparecerem seis execuções:

| Evento | Workflow | O que faz |
| --- | --- | --- |
| Pull Request | `backend` | testes, lint e migrations; não publica imagem |
| Pull Request | `frontend` | lint, testes, build e auditoria; não publica imagem |
| Pull Request | `flutter` | analyze e testes dos dois apps e APK temporário de homologação; não publica release |
| tag `vX.Y.Z` | `backend` | testa e publica imagens no GHCR |
| tag `vX.Y.Z` | `frontend` | testa e publica imagens no GHCR |
| tag `vX.Y.Z` | `flutter` | testa, compila Windows/Linux e publica o Release |

Portanto, as execuções do Pull Request não duplicam o release. Elas são as
verificações exigidas para aprovar o merge. Somente as execuções iniciadas pela
tag entram nos jobs de publicação.

Na página do workflow Flutter de um Pull Request, `release-metadata` e
`build-garcom-apk` executam e deixam o APK nos artefatos temporários do Actions.
`build-windows`, `build-linux` e `publish-release` ficam ignorados porque exigem
tag ou disparo manual. Na execução da tag, todos os jobs são liberados em
sequência depois dos testes.

## Como publicar uma nova atualização

### 1. Escolher a versão

Use uma versão ainda não publicada. Exemplo:

```yaml
# flutter/pubspec.yaml
version: 1.0.34+32
```

Regras recomendadas:

- patch (`1.0.33` → `1.0.34`) para correção compatível;
- minor (`1.0.x` → `1.1.0`) para funcionalidade nova compatível;
- major (`1.x` → `2.0.0`) para mudança incompatível ou grande marco;
- nunca reutilizar uma tag ou sobrescrever binários de uma versão publicada.

### 2. Validar antes de publicar

No PowerShell, a partir da raiz:

```powershell
Push-Location flutter
flutter pub get
flutter analyze
flutter test
flutter build windows --release `
  --dart-define=API_BASE_URL=https://api.starchef.com.br/api/v1
Pop-Location
```

O Linux será compilado pelo runner Ubuntu. Quando houver uma máquina Linux de
homologação disponível, valide também o bundle nela antes de liberar para todos
os terminais.

Além dos testes automatizados, faça uma homologação curta:

- login e seleção do restaurante;
- abertura/recuperação de caixa;
- pedido de mesa, comanda e balcão;
- envio setorizado para produção;
- impressão em ao menos uma impressora real;
- fechamento e nova abertura do PDV;
- indicador de versão na barra lateral.

### 3. Commitar e enviar o código

```powershell
git add flutter/pubspec.yaml flutter/pubspec.lock
git commit -m "chore: prepara release v1.0.34"
git push origin SUA_BRANCH
```

Inclua no mesmo commit ou pull request todas as correções que farão parte do
release. Faça o merge na branch de entrega adotada pela equipe antes da tag.

### 4. Criar e enviar a tag

Confirme primeiro que o commit atual contém a versão correta:

```powershell
git status
git show HEAD:flutter/pubspec.yaml | Select-String '^version:'
```

Crie uma tag anotada no commit aprovado:

```powershell
git tag -a v1.0.34 -m "StarChef v1.0.34"
git push origin v1.0.34
```

Importante: a mesma tag `vX.Y.Z` também dispara os workflows do backend e do
frontend, publicando as imagens GHCR correspondentes. Só envie a tag quando o
conjunto completo estiver pronto para produção.

### 5. Acompanhar o GitHub Actions

No workflow `flutter`, os jobs executam nesta ordem:

1. `test` e `test-garcom`: dependências, analyze e testes dos dois apps;
2. `release-metadata`: lê as duas versões e compara a versão do PDV com a tag;
3. `build-windows`, `build-linux` e `build-garcom-apk`: geram instalador, ZIPs
   e o APK universal;
4. `publish-release`: reúne os pacotes, calcula hashes, gera o manifesto e
   publica o GitHub Release.

Se qualquer job falhar, `publish-release` não roda e o novo `latest.json` não é
publicado.

### 6. Conferir o release

O release deve conter exatamente estes arquivos para a versão:

```text
StarChef-PDV-Setup-X.Y.Z.exe
StarChef-PDV-Windows-vX.Y.Z.zip
StarChef-PDV-Linux-vX.Y.Z.zip
StarChef-Garcom-vA.B.C.apk
latest.json
```

`A.B.C` é a versão independente declarada em `flutter_garcom/pubspec.yaml`.
Abra o `latest.json` e confirme `version`, `tag`, `commit`, nomes e URLs.
Depois instale em um terminal de homologação e confira se o cabeçalho mostra a
tag instalada com o ícone verde.

### 7. Distribuir aos terminais

Faça rollout gradual:

1. um terminal de homologação;
2. um terminal de operação com baixo risco;
3. demais terminais após validar login, caixa, pedido e impressão.

Na primeira instalação do Windows, distribua o EXE. Nos terminais já
instalados, basta iniciar o PDV: ele encontrará o release mais recente e usará
automaticamente o ZIP correspondente. No Linux, inicie o executável por um
bundle instalado em pasta gravável pelo mesmo usuário.

## Build manual sem publicar release

O botão **Run workflow** permite executar `workflow_dispatch`. Ele aceita:

- `api_base_url`;
- `sentry_dsn`;
- `update_manifest_url`.

O disparo manual gera artefatos temporários do Actions para Windows, Linux e o
APK do garçom,
mas não executa `publish-release`: não cria tag, não cria GitHub Release e não
altera o `latest.json`. Use-o para homologação de build, nunca como substituto
da tag de produção.

## Conferência manual de integridade

No Windows:

```powershell
Get-FileHash .\StarChef-PDV-Setup-1.0.34.exe -Algorithm SHA256
```

No Linux:

```bash
sha256sum StarChef-PDV-Linux-v1.0.34.zip
```

Compare o resultado com o `sha256` do mesmo arquivo no `latest.json`. O hash
protege contra arquivo incompleto ou diferente do publicado. O PDV faz essa
conferência automaticamente para o ZIP; os comandos continuam úteis para
auditar manualmente um release ou validar o EXE do instalador.

## Diagnóstico

### A tag não inicia o workflow

- confirme o formato exato `vX.Y.Z`;
- confirme que a tag foi enviada com `git push origin vX.Y.Z`;
- abra a aba Actions e verifique se Actions está habilitado no repositório.

### `release-metadata` informa divergência

A parte antes de `+` no `pubspec.yaml` precisa ser igual à tag:

```text
pubspec: 1.0.34+32
tag:     v1.0.34
```

Não mova ou reaproveite uma tag já publicada. Corrija a versão em um novo
commit e crie uma nova tag.

### Build informa `API_BASE_URL não definido`

Cadastre `PDV_API_BASE_URL` em **Settings → Secrets and variables → Actions →
Variables**, ou informe `api_base_url` no disparo manual.

### PDV mostra `Atualização não verificada`

Verifique:

- acesso do terminal a `github.com` e `objects.githubusercontent.com`;
- existência de um release marcado como mais recente;
- presença do `latest.json` nos assets;
- JSON válido com `schema_version: 1`;
- presença de pacote `windows` ou `linux`, conforme o terminal;
- data, hora e certificados TLS da máquina.

O PDV continua operacional nesse estado. Clique no indicador para tentar
novamente depois de corrigir a rede.

### Release existe, mas o PDV ainda mostra a versão antiga

- abra `%LOCALAPPDATA%\StarChef\pdv.log` no Windows ou
  `~/.local/share/StarChef/pdv.log` no Linux e procure
  `pdv_auto_update_failed`;
- confira `updates/<versão>/update.log` no mesmo diretório de dados para saber
  se houve troca, rollback ou falha ao reiniciar;
- no Linux, confirme permissão de escrita na pasta do bundle e na pasta pai;
- confirme que o terminal executa o arquivo da pasta atualizada;
- no Windows, confira as propriedades do `starchef_pdv.exe`;
- no Linux, confira se o atalho ou serviço aponta para a pasta nova;
- compare o hash do pacote baixado com o manifesto.

### SmartScreen alerta no Windows

O instalador ainda não possui assinatura de código. O alerta pode continuar até
que um certificado de code signing seja incorporado ao pipeline.

## Rollback e correção de release

Durante a atualização automática, o helper renomeia a instalação atual para
`<pasta>.starchef-backup-<versão>-<pid>`, move o bundle preparado para o caminho
original e inicia o novo executável. A pasta anterior só é apagada depois que o
novo processo permanece ativo por oito segundos. Se a troca ou a inicialização
falhar, o helper remove somente a pasta nova controlada pela transação, restaura
o backup e reinicia a versão anterior.

Esse rollback local protege o terminal de falha de arquivo, permissão ou
inicialização. Ele não transforma um release defeituoso em release válido para
os demais terminais. Para corrigir o release publicado:

Não sobrescreva assets, não mova uma tag publicada e não reutilize uma versão.
O caminho seguro é:

1. corrigir o código;
2. incrementar versão e build, por exemplo `1.0.34+32` → `1.0.35+33`;
3. criar `v1.0.35`;
4. validar em homologação;
5. distribuir o novo patch.

Se for necessário voltar imediatamente um terminal, feche o aplicativo e
restaure o instalador/pasta anterior que já tenha sido homologado. A versão
anterior pode aparecer como desatualizada porque o manifesto continuará
apontando para o release mais novo; isso é esperado até a publicação da
correção.

## Arquivos relacionados

- `.github/workflows/flutter.yml`: build, manifesto e publicação;
- `flutter/pubspec.yaml`: versão do PDV;
- `flutter/lib/core/update/pdv_update_service.dart`: leitura e validação do
  manifesto;
- `flutter/lib/features/home/presentation/pdv_navigation_shell.dart`: indicador
  visual;
- `flutter/windows/installer/build_installer.ps1`: versão e geração do EXE;
- `flutter/windows/installer/starchef_pdv.iss`: comportamento do instalador.
