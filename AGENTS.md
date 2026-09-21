# Orientações para agentes de IA
use linguagem simpels e explique sempre com exemplos as duvidas e perguntas de forma de facil entendimento

> **Nesta branch (`release/v3.0.0`) não existem `flutter/` nem `flutter_garcom/`.**
> Eles foram substituídos por `pdv_desktop/` (PDV Windows/Linux) e
> `pdv_mobile/` (atendimento móvel), que falam direto com o backend, sem
> operação offline. As pastas antigas seguem nas outras branches.


Este arquivo vale para todo o monorepo StarChef.

## Documentação obrigatória por assunto

Antes de alterar versão, atualização do PDV, manifesto, GitHub Actions de
release, instalador Windows, pacote Linux ou criação de tag, leia por completo:

- `docs/PDV_UPDATE_RELEASE.md`

Esse é o documento canônico para atualização e publicação do PDV. Mantenha-o
sincronizado sempre que o contrato do `latest.json`, os nomes dos artefatos, as
variáveis do Actions, os jobs ou o procedimento de release mudarem.

Não coloque instruções de atualização/release no `DOC.md`. Esse assunto deve
continuar isolado em `docs/PDV_UPDATE_RELEASE.md`, salvo pedido explícito do
usuário para mudar essa organização.

Para assuntos técnicos mais amplos, use também a documentação específica:

- `docs/FLUTTER_DESKTOP.md`: arquitetura operacional do desktop;
- `docs/FLUTTER_PDV_TECNICO.md`: módulos e implementação interna do PDV;
- `docs/PDV_OFFLINE_SCALE_ARCHITECTURE.md`: offline, topologia e balanças;
- `docs/BACKEND.md`: API e serviços do backend;
- `docs/FRONTEND.md`: retaguarda web;
- `docs/TESTE_CARGA.md`: teste de carga manual das quatro frentes (`loadtest/`);
- `docs/TESTE_CARGA_PDV.md`: teste de carga do nucleo do PDV (histórico da
  linhagem offline; a suíte vivia em `flutter/loadtest/`, que não existe
  nesta branch);
- `docs/ANALISE_DE_RISCOS.md`: os defeitos que a carga achou, o que foi corrigido e o que segue aberto;
- `docs/SINCRONIZACAO.md`: sincronização backend-to-backend (loja ⇄ nuvem),
  a matrícula do nó, a outbox durável e a recuperação do que não subiu;
- `docs/CONTA_AGRUPADA_COMANDAS.md`: pagar várias comandas num pedido só —
  `OrderMerge`, o estado do item na comanda, a cozinha lendo a origem e a
  balança que pesa para a comanda.

## Regra da sincronização

Ao criar um model novo em `backend/apps/`, ele precisa de decisão explícita:
entra em `apps/synchronization/catalog.py` (sincroniza) ou em
`apps/synchronization/decisions.py` (não sincroniza, com o motivo).
`manage.py sync_check_registry` falha o deploy se ficar sem nenhuma das duas.

No PostgreSQL, rode também `manage.py sync_install_triggers` depois do
`migrate` (é idempotente): são elas que capturam escrita feita por fora do ORM.
O compose de `docker/local/` já faz isso no boot.

## Regras do release do PDV

- A versão vem de `pdv_desktop/pubspec.yaml` no formato `X.Y.Z+N`.
- A tag de release correspondente é `vX.Y.Z`; ela não inclui o build number.
- Nunca crie, mova, apague ou reutilize uma tag sem autorização explícita do
  usuário. Uma tag dispara publicação externa de backend, frontend e PDV.
- Um Pull Request executa validações, mas não publica release.
- `workflow_dispatch` gera artefatos temporários, mas não publica o
  `latest-desktop.json` nem cria GitHub Release.
- A tag executa os QUATRO workflows do monorepo — `backend`, `frontend`,
  `pdv-desktop` e `pdv-mobile` —, cada um independente. No `pdv-desktop` o
  fluxo é `test` → `release-metadata` → builds Windows/Linux →
  `publish-release`; no `pdv-mobile`, `test` → `release-metadata` →
  `build-apk` → `publish-mobile`.
- **Os dois workflows do Flutter são independentes: um NÃO chama o outro.**
  Eles reagem à mesma tag e anexam ao mesmo GitHub Release, serializados pelo
  grupo de `concurrency` `gh-release-<tag>`, que os dois compartilham. Se você
  alterar esse grupo, altere nos DOIS arquivos — grupos diferentes trazem de
  volta a corrida na criação do Release (um dos dois recebe 422).
- Cada produto publica o manifesto dele: `latest-desktop.json` pelo
  `pdv_desktop.yml` e `latest-mobile.json` pelo `pdv_mobile.yml`. Nenhum dos
  dois pode escrever `latest.json`: esse nome é da linhagem 1.8.x do PDV
  offline, que segue em produção nas outras branches.
- O pipeline deve falhar se a tag não corresponder à versão pública do
  `pubspec.yaml`.
- `backend.yml`/`frontend.yml` decidem se reconstroem a imagem comparando o
  conteúdo com a tag anterior (achada pelo NOME — a mais recente que não seja
  esta —, nunca por commit ancestral do SHA anterior, que fica confuso quando
  uma tag é apagada e recriada, como já foi preciso na v1.7.2 e na v1.8.1).
  Esse passo de "o que mudou" precisa rodar com `working-directory:
  ${{ github.workspace }}` (a raiz do repo) — ele fica DENTRO de um job cujo
  default é `working-directory: backend`/`frontend`, e `git diff -- backend
  .github/workflows/backend.yml` executado de dentro de `backend/` vira
  `backend/backend` e `backend/.github/workflows/backend.yml`: pathspecs que
  não existem, diff sempre vazio, "nada mudou" sempre verdadeiro. Esse bug
  esteve presente desde que o passo foi criado (`efddcb5`, ago/2026): toda
  release com uma tag anterior — ou seja, a partir da segunda — só re-etiquetou
  a imagem antiga, nunca reconstruiu de verdade, até a v1.8.3 corrigir (a
  v1.8.2 tentou consertar só a comparação por nome e não pegou este bug — foi
  preciso conferir o resultado real do Actions, não só simular o script
  localmente sem o `working-directory` do job). Sempre que mexer nesse passo,
  reproduza o `cd` do job antes de validar o comando localmente, e confirme
  depois consultando as runs publicadas (a API do Actions é pública neste
  repositório), não só a lógica isolada. Preferir uma tag NOVA a apagar/recriar
  uma existente continua sendo mais seguro, mesmo com o achado por nome: uma
  tag nova nunca depende de nenhuma corrida entre a exclusão do ref antigo e a
  criação do novo.

## Contrato de atualização atual

- O PDV verifica automaticamente se existe versão nova durante a inicialização.
- A verificação nunca deve bloquear login, venda, caixa ou impressão quando a
  rede/GitHub estiver indisponível.
- Quando existe uma versão nova, o PDV baixa o ZIP portátil da plataforma,
  valida tamanho e SHA-256, prepara o bundle e bloqueia a operação somente
  durante esse fluxo de atualização.
- Um processo auxiliar fecha as janelas do mesmo executável, troca o bundle,
  reinicia o PDV e restaura a versão anterior se a nova encerrar durante a
  validação inicial.
- Windows publica instalador EXE recomendado e ZIP portátil alternativo.
- O EXE é destinado à instalação manual; o atualizador automático do Windows
  escolhe o ZIP para permitir rollback transacional.
- Linux publica ZIP como pacote recomendado.
- O Release publica `latest.json` com versão, tag, commit, URLs, tamanhos e
  SHA-256.
- A URL padrão do manifesto é
  `https://github.com/<owner>/<repo>/releases/latest/download/latest.json` e
  pode ser substituída por `PDV_UPDATE_MANIFEST_URL` no build.
- O APK do atendimento móvel não faz parte do manifesto do PDV: ele tem o
  `latest-mobile.json`, publicado pelo próprio `pdv_mobile.yml`.
- O `pdv_mobile.yml` roda sozinho na tag; o `pdv_desktop.yml` não o chama mais.
  O APK continua saindo no mesmo GitHub Release.
- Em tags, a assinatura exige os quatro Secrets `GARCOM_*` e o job **falha** sem
  eles — ou se o APK sair com `CN=Android Debug`. Nunca publique APK de
  produção com a chave de debug: ele não instala por cima do app já instalado.
- Backend, frontend e APK só são reconstruídos numa tag quando os arquivos do
  componente mudaram desde a tag anterior. Quem não é reconstruído é
  re-etiquetado (imagens) ou herdado do manifesto anterior (APK). O PDV é
  sempre reconstruído, porque a tag é a versão dele.
- O `publish-mobile` roda em TODA tag, mesmo sem APK novo: ele precisa
  reescrever o `latest-mobile.json` no release novo. Sem isso a URL
  `releases/latest/download/latest-mobile.json` passa a responder 404 e o app
  perde a checagem de atualização.

## Arquivos que precisam permanecer coerentes

- `.github/workflows/pdv_desktop.yml`;
- `.github/workflows/pdv_mobile.yml`;
- `pdv_mobile/pubspec.yaml`, `pdv_mobile/android/app/build.gradle.kts`
  e `pdv_mobile/README.md`;
- `pdv_desktop/pubspec.yaml` e `pdv_desktop/pubspec.lock`;
- `pdv_desktop/lib/core/update/pdv_update_service.dart`;
- `pdv_desktop/lib/core/update/pdv_auto_updater.dart`;
- `pdv_desktop/lib/core/update/pdv_update_installer.dart`;
- `pdv_desktop/lib/features/home/presentation/pdv_navigation_shell.dart`;
- `pdv_desktop/windows/installer/build_installer.ps1`;
- `pdv_desktop/windows/installer/starchef_pdv.iss`;
- `docs/PDV_UPDATE_RELEASE.md`.

Ao alterar o schema do manifesto, atualize na mesma mudança o gerador do
Actions, o parser Flutter, os testes e o exemplo JSON da documentação.


## Padrões de código (vale para as quatro superfícies)

O documento completo é `docs/PADROES_DE_CODIGO.md`. O que **reprova o merge**
está abaixo; leia o documento para os porquês e os exemplos.

### O critério que decide tudo

> **Entra o que aponta defeito. Fica de fora o que só discorda de uma escolha.**

Vale para regra de lint, para comentário de revisão e para o que se exige num
PR. Regra que grita em cima de decisão deliberada é desligada na primeira
urgência — e aí para de pegar até o que importava.

### Máximo 200 linhas por arquivo

Passou disso, quebre em módulos com **uma responsabilidade cada**. O corte é por
assunto, não por camada.

201 arquivos já passavam disso quando a regra passou a ser medida, então a
trava é uma **catraca**, não um muro:

```bash
python scripts/check_tamanho_de_arquivo.py            # confere (roda no CI)
python scripts/check_tamanho_de_arquivo.py --atualizar  # ao baixar a dívida
```

O que já era grande está na linha de base e não reprova ninguém. **Arquivo novo
acima do limite não tem exceção** — quebre. Arquivo que já era grande e cresceu
também reprova: quebre, ou rode `--atualizar` e deixe o crescimento visível no
diff, para quem revisa poder perguntar por quê. O que não pode é crescer em
silêncio.

### As cinco que custam dinheiro

1. **Dinheiro nunca é `float`.** `Decimal` ou inteiro de centavos. Arredonde
   onde o valor nasce, não na gravação — o SQLite não trunca como o Postgres, e
   os dois lados discordavam por um centavo.
2. **Total que é soma de vários soma valores já arredondados.** Dois pedidos de
   R$ 10,05 com 10% dão R$ 2,02, não R$ 2,01.
3. **Escrita concorrente:** `transaction.atomic` + lock ordenado por UUID, e
   **releia o estado depois do lock**. Conferir antes de travar não impede
   corrida nenhuma.
4. **A defesa contra dois operadores é do BANCO** (índice único condicional),
   nunca um `if` — o `if` roda antes do lock do outro.
5. **409 é conflito de estado; 400 é entrada errada.** O PDV reenvia 400 para
   sempre, então um conflito devolvido como 400 vira laço infinito.

### Sincronização: a regra que mais some

Nada está pronto enquanto o dado novo não sincronizar.

- **Model novo** precisa de decisão em `catalog.py` ou `decisions.py`
  (`manage.py sync_check_registry` reprova o deploy).
- **Campo novo não tem trava automática.** Confira que ele entra no payload e
  escreva o teste — foi assim que se achou `ScaleReading.notes` nunca chegando
  à nuvem.
- **`QuerySet.update()` não dispara signal**, logo não gera evento.
- **Não declare append-only o que tem ciclo de vida.** `cash_movement` era
  `immutable=True` e tem `pending → approved → cancelled`: as transições
  morriam na chegada e o caixa da nuvem fechava o turno com outro valor.

### Comentário, nome e teste

- O comentário explica **por que**, nunca **o quê**. Mudou a linha, revise o
  comentário dela no mesmo commit.
- O domínio é escrito em **português** (`comanda`, `sangria`, `pedido`): é o
  vocabulário de quem opera o caixa.
- Nome de teste é uma frase, e o docstring conta o defeito que ele impede.
- **Escreva o teste antes da correção e veja-o falhar.** Ao corrigir um defeito,
  reverta a correção por um instante e confirme que o teste pega. Um teste que
  nunca falhou não provou nada.
- `pytest.raises(Exception)` é proibido: passa até com `AttributeError` de
  digitação. Nomeie a exceção.

### Onde cada regra vive

| Superfície | Configuração | Comando |
| --- | --- | --- |
| `backend/` | `backend/pyproject.toml` | `ruff check .` |
| `frontend/` | `frontend/eslint.config.js` | `npm run lint` |
| `pdv_desktop/` | `pdv_desktop/analysis_options.yaml` | `flutter analyze` |
| `pdv_mobile/` | `pdv_mobile/analysis_options.yaml` | `flutter analyze` |
| todas | `scripts/tamanho_de_arquivo.baseline.json` | `python scripts/check_tamanho_de_arquivo.py` |

Ao ligar ou desligar uma regra, **escreva o motivo ao lado dela** no arquivo de
configuração. Os três arquivos já seguem isso, inclusive registrando as regras
que foram medidas, pioraram o código e por isso saíram.

### Modelos de issue e PR

`.github/PULL_REQUEST_TEMPLATE.md` e `.github/ISSUE_TEMPLATE/`. O PR pede o que
foi **rodado**, com a saída — "testei" não é verificação.

## Validação mínima

Para mudanças no PDV ou no release, execute em `flutter/`:

```powershell
flutter pub get
flutter analyze
flutter test
```

Quando houver mudança de build Windows, valide também o comando
`flutter build windows --release` com a `API_BASE_URL` adequada. Para Linux,
mantenha o job Ubuntu do Actions e suas dependências coerentes com o bundle.

Antes de concluir:

- execute `git diff --check`;
- valide os workflows contra o SCHEMA do GitHub, não só como YAML:

  ```bash
  python -m check_jsonschema --builtin-schema vendor.github-workflows .github/workflows/*.yml
  ```

  `yaml.safe_load` aceita coisas que o GitHub recusa. Um `env:` sem filhos vira
  `env: null` — YAML perfeito, workflow inválido: o arquivo INTEIRO é rejeitado,
  o workflow some da lista de gatilhos e aparece no Actions com o caminho no
  lugar do nome. Foi assim que a v3.0.0 saiu sem APK;
- valide o JSON de exemplo quando for alterado;
- não versione `artifacts/`, builds, instaladores, ZIPs ou APKs;
- informe claramente se houve apenas commit/push de branch ou também uma
  publicação por tag.
