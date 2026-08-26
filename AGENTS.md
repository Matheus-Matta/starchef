# Orientações para agentes de IA

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
- `docs/FRONTEND.md`: retaguarda web.

## Regras do release do PDV

- A versão vem de `flutter/pubspec.yaml` no formato `X.Y.Z+N`.
- A tag de release correspondente é `vX.Y.Z`; ela não inclui o build number.
- Nunca crie, mova, apague ou reutilize uma tag sem autorização explícita do
  usuário. Uma tag dispara publicação externa de backend, frontend e PDV.
- Um Pull Request executa validações, mas não publica release.
- `workflow_dispatch` gera artefatos temporários, mas não publica o
  `latest.json` nem cria GitHub Release.
- A tag executa os três workflows do monorepo. No Flutter, o fluxo esperado é
  `test` → `release-metadata` → builds Windows/Linux → `publish-release`.
- O pipeline deve falhar se a tag não corresponder à versão pública do
  `pubspec.yaml`.

## Contrato de atualização atual

- O PDV verifica automaticamente se existe versão nova ao carregar a tela
  principal.
- A verificação nunca deve bloquear login, venda, caixa ou impressão quando a
  rede/GitHub estiver indisponível.
- Download e instalação ainda são manuais. Não descreva o sistema como
  auto-instalação enquanto esse comportamento não estiver implementado e
  testado.
- Windows publica instalador EXE recomendado e ZIP portátil alternativo.
- Linux publica ZIP como pacote recomendado.
- O Release publica `latest.json` com versão, tag, commit, URLs, tamanhos e
  SHA-256.
- A URL padrão do manifesto é
  `https://github.com/<owner>/<repo>/releases/latest/download/latest.json` e
  pode ser substituída por `PDV_UPDATE_MANIFEST_URL` no build.
- O APK do aplicativo do garçom não faz parte do manifesto do PDV.

## Arquivos que precisam permanecer coerentes

- `.github/workflows/flutter.yml`;
- `flutter/pubspec.yaml` e `flutter/pubspec.lock`;
- `flutter/lib/core/update/pdv_update_service.dart`;
- `flutter/lib/features/home/presentation/pdv_navigation_shell.dart`;
- `flutter/windows/installer/build_installer.ps1`;
- `flutter/windows/installer/starchef_pdv.iss`;
- `docs/PDV_UPDATE_RELEASE.md`.

Ao alterar o schema do manifesto, atualize na mesma mudança o gerador do
Actions, o parser Flutter, os testes e o exemplo JSON da documentação.

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
- valide a sintaxe do workflow e o JSON de exemplo quando forem alterados;
- não versione `artifacts/`, builds, instaladores, ZIPs ou APKs;
- informe claramente se houve apenas commit/push de branch ou também uma
  publicação por tag.
