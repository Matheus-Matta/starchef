# StarChef PDV Mobile

Aplicativo móvel de atendimento baseado no visual do antigo app do garçom,
sem dependência de um Caixa Principal na rede local.

## Comunicação

- O login, as consultas e as alterações de pedidos vão diretamente ao backend.
- A URL padrão é `https://api.starchef.com.br/api/v1`.
- A URL pode ser alterada em **Configurar servidor** na tela de login ou em
  **Conta → Servidor da API** depois da entrada.
- Alterar o servidor durante uma sessão encerra o login para impedir que um
  token de um ambiente seja enviado a outro.
- Alterações feitas sem conexão ficam na fila local e são reenviadas à mesma
  API com uma chave de idempotência.

## Impressão pelo telefone

O agente móvel consulta a lista de impressoras e a fila do restaurante no
backend. Ele só assume impressoras ativas com conexão `network`, endereço IP e
porta válidos e `auto_print` habilitado. O telefone consome exclusivamente
novas comandas (`kitchen_ticket`/`bar_ticket`) e cancelamentos de cozinha
(`kitchen_cancellation`), seguindo os tipos e o roteamento por impressora/setor
definidos pelo backend. Recibos, fechamento de caixa, pesagem, DANFE e testes
permanecem com o PDV Desktop. Trabalhos `manual_only` também são ignorados.

O driver `escpos` habilita código de barras e guilhotina; o
driver `browser` recebe texto puro, como no transporte TCP do desktop.
Impressoras Windows/USB ou seriais são deixadas para outro agente compatível.

Para cada trabalho, o app:

1. consulta `/print-jobs/`;
2. reserva o trabalho em `/print-jobs/{id}/claim/`;
3. envia o `text_content` em ESC/POS à impressora TCP/IP;
4. confirma em `mark-printed` somente depois da gravação no socket;
5. libera a reserva em `release` quando a comunicação física falha.

Android solicita acesso a dispositivos Wi-Fi próximos. Se a permissão for
negada, o app ainda mostra a lista recebida do backend, informa a limitação e
oferece abrir as configurações do sistema. No iOS, o primeiro acesso ao IP de
uma impressora usa a permissão de rede local declarada no `Info.plist`.

## Desenvolvimento

```powershell
flutter pub get
flutter analyze
flutter test
flutter run
```

Para um backend local HTTP, informe por exemplo
`http://192.168.1.10:8000/api/v1`. O aparelho e a impressora precisam alcançar
a mesma rede local para que o envio TCP funcione.
