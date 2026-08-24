# StarChef Garçom

App de salão: **tirar pedido e consultar/editar pedido**. Sem pagamento — receber
é do caixa, que tem gaveta, maquininha e impressora fiscal.

## Por que o app não fala direto com a nuvem

Quem imprime é o **Caixa Principal** (o PDV desktop da loja). Um celular não
imprime em impressora USB do balcão, então o pedido tirado no salão é entregue
ao principal, que grava, imprime na cozinha e sincroniza com a retaguarda.

```
  celular do garçom                 Caixa Principal (PDV)            Retaguarda
 ┌──────────────────┐   HMAC LAN   ┌────────────────────┐   HTTPS   ┌──────────┐
 │ pedido / itens   │ ───────────► │ grava + imprime    │ ────────► │  Django  │
 │ envio p/ cozinha │  :47832      │ (fila offline)     │           │          │
 └────────┬─────────┘              └────────────────────┘           └────┬─────┘
          │                                                              │
          └──────────────── login (JWT) e leitura de reserva ────────────┘
```

- **Escrita** (abrir pedido, lançar item, cancelar item, enviar para a cozinha):
  **sempre** pelo Caixa Principal. Se ele estiver fora do ar, o lançamento falha
  na hora e o garçom sabe — melhor que um pedido aceito no celular que a cozinha
  nunca recebeu.
- **Leitura** (pedidos, mesas, catálogo): tenta o principal primeiro — é a mesma
  verdade que o caixa enxerga, e funciona com a internet da loja caída — e cai
  para o backend quando o principal não responde.

O protocolo é o mesmo que o PDV já usa entre Caixa Cliente e Caixa Principal
(`flutter/lib/features/topology/services/local_topology_service.dart`):
HMAC-SHA256 por requisição com timestamp e nonce, e resposta também assinada.

## As duas etapas de entrada

```
  login (usuário e senha)  ──►  conectar ao caixa  ──►  pedidos abertos
   quem é o garçom              (uma vez por aparelho)
```

O Caixa Principal é configurado **depois** do login, em tela própria, por dois
motivos: a requisição de teste vai assinada com conta, operador e restaurante —
que só existem depois de o backend dizer quem é o garçom — e o pareamento é do
**aparelho**, não da pessoa.

Disso decorre o comportamento do dia a dia:

- **Cadastra-se uma vez por aparelho.** Normalmente pelo gerente, na entrega do
  celular ao salão.
- **Sair da conta não apaga o caixa.** Trocou o garçom no fim do turno? O
  próximo entra com o usuário dele e cai direto na lista de pedidos.
- **Dá para trocar depois** em ⋮ → *Trocar Caixa Principal*, sem deslogar —
  para quando a loja muda o computador do caixa ou gera uma chave nova.

| O quê | Onde | Por quê |
|---|---|---|
| Endereço da retaguarda | `.env` (`BACKEND_URL`), embarcado como asset | É igual para toda a rede e não é segredo |
| IP, porta e senha do Caixa Principal | tela de pareamento, guardada no cofre do aparelho | Muda de loja para loja; a senha não pode viajar dentro do APK |

```bash
flutter pub get
flutter run                     # usa o BACKEND_URL do .env
```

O `.env` aceita o domínio (`http://192.168.0.10:8001`) ou a URL completa; sem
caminho, o app completa com `/api/v1`.

Sessão e pareamento ficam no cofre do sistema (`flutter_secure_storage`) em
chaves separadas — é o que permite apagar um sem tocar no outro no logout.
Nunca em SharedPreferences: o aparelho circula pelo salão e a chave de
pareamento dá direito de gravar pedidos na loja inteira.

## Requisitos do lado do caixa

1. O PDV precisa estar como **Caixa Principal** com a rede local liberada
   (Configurações → Rede local: chave de pareamento gerada e rede confiável
   confirmada). A chave gerada ali é a "senha do Caixa Principal" pedida no
   login do app.
2. Celular e caixa na **mesma rede Wi-Fi privada** — o principal recusa
   conexões que não venham de IPv4 privado.
3. O garçom precisa de um usuário com **restaurante vinculado** no cadastro.

## Rede nas plataformas

O Caixa Principal é HTTP em claro num IP privado — os dois sistemas bloqueiam
isso por padrão, então o app declara:

- **Android**: `INTERNET` no manifesto principal (o template do Flutter só
  declara em debug/profile — sem isso o release fica sem rede) e
  `network_security_config.xml` liberando tráfego em claro. A configuração do
  Android não aceita faixas de IP, e o endereço do caixa muda de loja para
  loja, então a permissão é do app; o que segura o risco é a assinatura HMAC
  em cada requisição e a resposta verificada.
- **iOS**: `NSAllowsLocalNetworking` (libera só endereços locais, mantendo o
  ATS ativo para a retaguarda) e `NSLocalNetworkUsageDescription`, exigido do
  iOS 14 em diante para falar com aparelhos da rede local.

## Estrutura

```
lib/
  core/
    config/app_env.dart          .env (só o backend)
    network/api_client.dart      backend: login e leitura de reserva
    relay/principal_client.dart  LAN: protocolo do Caixa Principal
    relay/relay_signature.dart   HMAC — cópia deliberada do PDV, com teste
    storage/session_store.dart   cofre do aparelho
    theme/                       tokens shadcn compartilhados com o PDV
  features/
    auth/                        login (credencial + pareamento)
    orders/                      lista, pedido, lançamento, envio à cozinha
    menu/                        busca de produto, quantidade, observação
```

## Gerar o APK

```bash
flutter build apk --release --split-per-abi   # 3 APKs menores, um por arquitetura
flutter build apk --release                   # 1 APK universal (serve em qualquer aparelho)
```

Para instalar no aparelho do garçom: **arm64** cobre praticamente todo celular
atual; **arm32** só para aparelhos antigos; o **universal** é o à prova de erro,
ao custo de ~50 MB. Como a instalação é fora da Play Store, o aparelho precisa
permitir "instalar apps desconhecidos" para o app que estiver abrindo o arquivo
(navegador, gerenciador de arquivos ou WhatsApp).

### Assinatura

O release é assinado com `android/starchef-garcom-release.jks`, configurado em
`android/key.properties`. **Os dois estão no `.gitignore` e precisam de backup
fora do repositório**: sem essa chave não existe atualização de um app já
instalado — só desinstalar e instalar de novo, perdendo a sessão do aparelho.

Num clone sem esses arquivos o build continua funcionando, caindo na chave de
debug (serve para testar, não para distribuir). Se o `key.properties` existir
mas estiver ilegível, o build **falha** em vez de assinar com debug em
silêncio — foi assim que um release saiu com a chave errada sem ninguém notar.

## Testes

```bash
flutter test
```

`test/relay_signature_test.dart` trava a assinatura contra uma reimplementação
independente do algoritmo do PDV — se alguém mudar a ordem dos campos de um lado
só, o principal passaria a responder 401 em tudo.
`test/principal_client_test.dart` sobe um Caixa Principal de mentira e exercita
o protocolo inteiro, inclusive senha errada, impostor na rede e principal fora
do ar.
`test/session_flow_test.dart` trava a ordem e a permanência das etapas: login
antes do pareamento, pareamento sobrevivendo ao logout e ao fechar o app, e
caixa que não responde não sendo gravado.

## Limitações conhecidas

- O principal executa a operação com a credencial **dele**, então o pedido fica
  registrado com o usuário do caixa. O ator viaja assinado em cada requisição,
  mas ainda não é usado para atribuir autoria no backend.
- Sem fila offline no celular: sem o principal, não se lança. É uma decisão —
  duas filas independentes é o caminho mais curto para pedido duplicado.
- Produto vendido por kg fica fora do lançamento pelo celular (depende da
  balança do balcão), assim como adicionais avulsos e insumos.
