# StarChef PDV Desktop

Terminal de venda **conectado**. Toda leitura e toda escrita vão ao backend na
hora, e a resposta do servidor é a verdade. Se a rede cair, a operação falha na
cara do operador com mensagem — é melhor recusar uma venda do que registrá-la
num lugar que ninguém mais enxerga.

É uma linhagem separada do PDV offline que continua em produção — aquele vive
em outra branch (`flutter/`), não nesta. Os dois convivem: nomes de
executável, versões e canais de atualização diferentes (aqui,
`latest-desktop.json`).

## O que este app NÃO tem

Nada disso existe aqui, e a ausência é o ponto:

- **Banco local de negócio.** Sem SQLite, sem pedidos/caixa/produtos em disco.
- **Fila de saída.** Nenhuma venda espera a rede para subir.
- **Cache de leitura.** Um preço de ontem numa tela de venda é pior do que uma
  tela vazia com um aviso.
- **Caixa Principal / Caixa Secundário.** Não há rede local entre terminais,
  relay, pareamento nem topologia. Cada terminal fala direto com o backend.
- **Login offline.** Quem autentica é o servidor, sempre.
- **Documentos montados aqui.** Recibo, comanda de cozinha, nota de pesagem,
  comprovantes de caixa e DANFE são renderizados pelo BACKEND.

## O que fica em disco

Só o que é do computador, não do negócio:

| O quê | Onde | Por quê |
| --- | --- | --- |
| Fila da impressora | `print_queue.json` | Entre receber o texto e o papel sair existe o mundo físico: papel acabando, cabo solto. Um cupom perdido aí não tem como ser pedido de novo. |
| Templates de impressão | `print_templates/` | Evita uma ida ao servidor a cada cupom. |
| Vínculos de periférico | `device_bindings.json` | Qual leitor está em qual porta DESTA máquina. |
| Sessão e credenciais | cofre do SO (+ arquivo no Linux) | Para o operador não relogar a cada abertura. |
| Preferências | `preferences.json` | Tema, escala, atalhos, endereço do backend e a identidade desta instalação. |

## Impressão

O backend monta o documento — é ele que sabe o preço, o imposto e o layout. O
PDV escolhe a impressora e põe no papel, porque é ele que enxerga o equipamento
do balcão.

Vários terminais da mesma unidade podem servir a fila ao mesmo tempo: cada
trabalho é **reservado** no servidor antes de virar papel
(`POST /print-jobs/{id}/claim/`), e quem perde a corrida ignora aquele cupom.
Sem isso, dois PDVs enxergariam o mesmo pendente e a comanda sairia duas vezes
na cozinha.

## Endereço do backend

Definido em ordem de prioridade:

1. O campo na tela de login (grava em `preferences.json`);
2. `--dart-define=API_BASE_URL=...` no build;
3. o padrão do `AppConfig`.

## Rodar

```bash
flutter pub get && flutter run -d windows
```

```bash
flutter analyze && flutter test
```

## Atualização automática

O manifesto padrão é `latest-desktop.json` — **não** o `latest.json` do PDV
1.8.x. Um manifesto só faria o app antigo enxergar esta versão como
atualização e trocar um PDV que vende sem internet por um que não vende.
Sobrescreva com `--dart-define=PDV_UPDATE_MANIFEST_URL=...`.

A troca é feita **item a item**, sem renomear o diretório de instalação:
atalhos, entrada no menu Iniciar, regra de firewall e exclusão do antivírus
continuam válidos. Renomear a pasta era o que, no Windows, produzia uma pasta
nova aninhada dentro da instalação quando um único arquivo estava preso.
