/**
 * Identidade desta instalação do StarChef no navegador.
 *
 * Antes, a abertura de caixa mandava `navigator.userAgent` como
 * `device_identifier`. Isso identifica o NAVEGADOR, não a máquina: dois perfis
 * do mesmo Chrome mandam a mesma string, e a própria MDN desaconselha usá-la
 * como identidade. Servia para preencher um campo, nunca para decidir quem é
 * dono de uma sessão de caixa.
 *
 * Aqui a identidade é um UUID gerado com `crypto.randomUUID()` e guardado no
 * perfil do navegador. Ele identifica **a instalação do StarChef naquele
 * perfil**, não o computador físico: limpar os dados do site ou usar uma
 * janela anônima cria uma instalação nova. Isso não permite abrir um segundo
 * caixa — a exclusividade é garantida no servidor (índice parcial + transação)
 * e no Caixa Principal, não aqui. O que se perde é só a recuperação
 * automática: a sessão anterior passa a exigir uma transferência gerencial,
 * que é exatamente o caminho previsto para "o navegador perdeu seus dados".
 */
const INSTALLATION_KEY = "starchef-terminal-installation";
const NAME_KEY = "starchef-terminal-name";

/** Canal de avisos entre abas do mesmo navegador. */
const CHANNEL_NAME = "starchef-cash-session";

function readStorage(key) {
  try {
    return localStorage.getItem(key) || "";
  } catch {
    // Modo anônimo restrito ou armazenamento bloqueado: seguimos sem
    // identidade persistente em vez de derrubar a tela.
    return "";
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* sem persistência: a identidade vale só nesta aba */
  }
}

function randomUuid() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // `randomUUID` exige contexto seguro. Em HTTP local (rede da loja) caímos
  // para bytes aleatórios do mesmo `crypto`, que continua disponível.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

let cachedInstallationId = "";

/** UUID desta instalação, criado na primeira vez e reutilizado depois. */
export function terminalInstallationId() {
  if (cachedInstallationId) return cachedInstallationId;
  let id = readStorage(INSTALLATION_KEY);
  if (!id) {
    id = randomUuid();
    writeStorage(INSTALLATION_KEY, id);
  }
  cachedInstallationId = id;
  return id;
}

/** Nome amigável deste terminal ("Balcão 01"), quando a loja já o definiu. */
export function terminalName() {
  return readStorage(NAME_KEY) || defaultTerminalName();
}

export function setTerminalName(name) {
  writeStorage(NAME_KEY, String(name || "").trim());
}

/**
 * Nome padrão até alguém batizar o terminal. Usa um trecho do UUID em vez do
 * user agent: "Navegador a1b2c3" é curto e estável, e a string do navegador
 * seria ilegível dentro de "já está aberto por João no terminal ...".
 */
function defaultTerminalName() {
  return `Navegador ${terminalInstallationId().slice(0, 6)}`;
}

/** Campos de identidade enviados junto de toda operação de caixa. */
export function terminalPayload() {
  return {
    terminal_installation_id: terminalInstallationId(),
    terminal_name: terminalName(),
    terminal_type: "web",
    terminal_role: "web",
    // Mantido para servidores que ainda leem o campo antigo.
    device_identifier: terminalInstallationId(),
  };
}

/**
 * Executa `task` com exclusividade entre as abas deste navegador.
 *
 * Web Locks coordenam abas da mesma origem — duas abas abertas no mesmo caixa
 * deixam de mandar dois POSTs de abertura porque o operador clicou duas vezes.
 * Isso NÃO substitui a trava do backend nem a do Caixa Principal: outro
 * computador, outro navegador e o replay da fila offline continuam passando
 * por elas. É uma proteção contra o clique duplicado, não contra a corrida
 * distribuída.
 */
export async function withCashLock(key, task) {
  const lockName = `starchef-cash:${key}`;
  if (!navigator.locks?.request) return task();
  return navigator.locks.request(lockName, task);
}

let channel = null;

function cashChannel() {
  if (channel !== null) return channel;
  channel = typeof BroadcastChannel === "function" ? new BroadcastChannel(CHANNEL_NAME) : undefined;
  return channel;
}

/** Avisa as outras abas que a sessão de caixa mudou. */
export function announceCashSessionChange(detail = {}) {
  cashChannel()?.postMessage({ type: "cash-session-changed", at: Date.now(), ...detail });
}

/**
 * Escuta mudanças vindas de outra aba. Devolve a função para parar de ouvir.
 *
 * Sem isto, fechar o caixa numa aba deixava a outra oferecendo sangria de uma
 * sessão que não existe mais — e o erro só aparecia no clique.
 */
export function onCashSessionChange(handler) {
  const target = cashChannel();
  if (!target) return () => {};
  const listener = (event) => {
    if (event.data?.type === "cash-session-changed") handler(event.data);
  };
  target.addEventListener("message", listener);
  return () => target.removeEventListener("message", listener);
}
