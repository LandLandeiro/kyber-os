/* =====================================================================
   KYBER — formatação compartilhada entre telas.

   Vocabulário: pt-BR, vírgula decimal, número sempre com unidade,
   rótulo em mono caixa alta. Nunca abreviar por preguiça de layout —
   as formas curtas daqui existem porque a coluna da tabela do índice
   tem largura fixa, não porque ficou grande.
   ===================================================================== */

import { state } from '../core/state.js';

const DIA = 864e5;

export const gb = (n) =>
  `${n.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`;

export const horas = (n) => `${n} h`;

const diasDesde = (iso) =>
  Math.floor((Date.now() - Date.parse(`${iso}T12:00:00`)) / DIA);

/** Forma longa, para o hero e a ficha. */
export function ultimoAcesso(iso) {
  if (!iso) return 'nunca jogado';
  const d = diasDesde(iso);
  if (d <= 0) return 'último acesso hoje';
  if (d === 1) return 'último acesso ontem';
  if (d < 14) return `último acesso há ${d} dias`;
  const semanas = Math.floor(d / 7);
  if (semanas < 9) return `último acesso há ${semanas} semanas`;
  return `último acesso em ${new Date(`${iso}T12:00:00`).toLocaleDateString('pt-BR')}`;
}

/** Forma curta em caixa alta, para a coluna ÚLTIMO do índice. */
export function ultimoAcessoCurto(iso) {
  if (!iso) return 'NUNCA';
  const d = diasDesde(iso);
  if (d <= 0) return 'HOJE';
  if (d === 1) return 'ONTEM';
  if (d < 14) return `${d} DIAS`;
  const semanas = Math.floor(d / 7);
  if (semanas < 9) return `${semanas} SEM.`;
  const meses = Math.floor(d / 30);
  return `${meses} ${meses === 1 ? 'MÊS' : 'MESES'}`;
}

export const NIVEL = { quiet: 'SILENCIOSO', nominal: 'EQUILIBRADO', hot: 'AGRESSIVO' };

/* Nível em três degraus de luminância, nunca na rampa de estado: a cor
   saturada é orçada por tela e já está gasta na régua. Ver identidade
   visual, seção 3 — "níveis usam luminância neutra". */
export const DEGRAUS = { quiet: 1, nominal: 2, hot: 3 };

/**
 * Anúncio temporário no lugar do contexto técnico do rodapé. É o stub
 * honesto das telas que ainda não existem: em vez de um botão que não
 * faz nada, um botão que diz o que ainda não foi construído.
 */
export function createNotice(contextLine, ms = 2400) {
  let timer = 0;

  const notice = (message) => {
    state.set('context', { text: message, alert: true });
    clearTimeout(timer);
    timer = setTimeout(() => state.set('context', contextLine), ms);
  };

  notice.restore = () => {
    clearTimeout(timer);
    state.set('context', contextLine);
  };

  notice.stop = () => clearTimeout(timer);

  return notice;
}

/** Ordenações da biblioteca. Compartilhada porque vitrine e índice
    precisam concordar sobre o que é "recentes". */
export function sortGames(games, key) {
  const list = [...games];
  if (key === 'nome') return list.sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
  if (key === 'tamanho') return list.sort((a, b) => b.sizeGB - a.sizeGB);
  /* recentes: nunca jogado vai para o fim da lista, não para o começo */
  return list.sort((a, b) => (b.lastPlayed ?? '').localeCompare(a.lastPlayed ?? ''));
}

/**
 * Vizinhos laterais declarados para uma linha de opções.
 *
 * A heurística de geometria custa `distância no eixo + desalinhamento × 2`,
 * e num painel de linhas com contagens diferentes de opções isso inverte:
 * medido no painel de Aparência, ir para a direita de DESLIGADO escolhia
 * uma opção da linha de cima (custo 442) em vez da opção ao lado (453),
 * porque ela estava um pouco à direita e perto na vertical.
 *
 * É exatamente a falha que o próprio documento de arquitetura antecipa —
 * "colunas irregulares vão produzir saltos inesperados; produção precisa
 * de vizinhança explícita por nó". Então a linha declara seus vizinhos e
 * a geometria fica só com o eixo vertical, onde ela acerta.
 *
 * @param {number} i      índice da opção na linha
 * @param {number} total  quantas opções a linha tem
 * @param {(j:number)=>string} seletor  seletor CSS da j-ésima opção
 */
export function vizinhosLaterais(i, total, seletor) {
  const attrs = [];
  if (i > 0) attrs.push(`data-focus-left="${seletor(i - 1)}"`);
  if (i < total - 1) attrs.push(`data-focus-right="${seletor(i + 1)}"`);
  return attrs.join(' ');
}
