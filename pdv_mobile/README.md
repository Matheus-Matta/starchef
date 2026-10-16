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
- A rodada da comanda (itens + enviar à cozinha) vai para a fila e sobe em
  segundo plano: a tela volta ao início na hora. A fila tenta 4 vezes; o que
  não sair fica em "não enviados" (ícone de nuvem no topo) para reenviar.
- Servidor da loja instável cai rápido para a nuvem: uma sonda ao `/health/`
  sem resposta, ou tempo esgotado (8 s) na loja, já desvia — e o app fica 5
  minutos na nuvem. A nuvem espera até 25 s. Escrita com tempo esgotado só
  é repetida na nuvem quando leva `id` (UUID do aparelho); sem isso, espera
  na fila.

## Tela inicial

Só comandas: todas, livres e em uso, com valor e quantidade de itens, 20 por
vez (carrega mais ao rolar). A busca pelo número fica fixa no topo. Tocar no
cartão abre a comanda com o cardápio já aberto. Não existe mais "Novo pedido".

Cada cartão em uso mostra O QUE a comanda tem: "3x X-Burger · 0,35 kg
Picanha · +2" (até 4 produtos, o mesmo produto somado). O resumo vem pronto do
servidor (`?preview=1` na lista e em `/commands/{id}/items/`,
`backend/apps/restaurants/command_preview.py`), sem abrir cartão por cartão.

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

Depois de enviar uma rodada à cozinha ou cancelar um item, o app acorda o
agente imediatamente. A varredura periódica continua como recuperação, mas o
pedido novo e o aviso de cancelamento não dependem de esperar o próximo ciclo.

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
