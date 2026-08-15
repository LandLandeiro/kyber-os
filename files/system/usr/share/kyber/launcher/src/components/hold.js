/* =====================================================================
   KYBER — componente · SEGURAR Ⓐ

   Atrito deliberado para ação que apaga dado ou encerra sessão. Um toque
   de Ⓐ é barato demais: o polegar já está no botão, e em 10-foot UI o
   reflexo chega antes da leitura. Segurar por 2 s obriga a decisão a
   durar mais que o reflexo, e mostra a conta correndo enquanto dura —
   soltar cancela sem consequência.

   O componente separa MECÂNICA de DESENHO de propósito. A mecânica é
   sempre a mesma; a caixa não é. Na tela 10 o alvo é um botão dedicado
   sobre fundo escuro, e o preenchimento avança em branco. Na tela 12 o
   alvo é uma linha de menu que JÁ ESTÁ branca por estar em foco, e o
   preenchimento avança em void — a mesma gramática espelhada, porque
   uma barra branca sobre linha branca não existiria.

   REGRA: destrutivo nunca recebe foco inicial, e nunca dispara no toque.
   ===================================================================== */

export const SEGURAR_MS = 2000;

/**
 * Mecânica do segurar. Não desenha nada e não escuta nada: quem liga na
 * descida e na subida de Ⓐ é a tela, porque só ela sabe se o alvo em
 * foco é o botão que pede pressão.
 *
 * @param {object}   o
 * @param {number}  [o.ms]           duração da pressão
 * @param {(t:number, ms:number) => void} [o.onProgresso]  t de 0 a 1
 * @param {() => void} [o.onConcluir]
 */
export function criarSegurar({ ms = SEGURAR_MS, onProgresso, onConcluir } = {}) {
  let inicio = 0;
  let raf = 0;

  function passo() {
    const t = Math.min(1, (performance.now() - inicio) / ms);
    onProgresso?.(t, ms);
    if (t >= 1) { parar(); onConcluir?.(); return; }
    raf = requestAnimationFrame(passo);
  }

  function parar() {
    cancelAnimationFrame(raf);
    raf = 0;
    inicio = 0;
  }

  return {
    /** @returns {boolean} true se começou agora (false se já estava em curso) */
    iniciar() {
      if (inicio) return false;
      inicio = performance.now();
      passo();
      return true;
    },
    /** @returns {boolean} true se havia o que cancelar */
    cancelar() {
      if (!inicio) return false;
      parar();
      onProgresso?.(0, ms);
      return true;
    },
    get emCurso() { return inicio !== 0; },
  };
}

/**
 * Marcação da barra. O rótulo é desenhado DUAS vezes e o de cima é
 * recortado pelo avanço: assim o texto inverte junto com o
 * preenchimento, em vez de sumir dentro dele.
 *
 * `classe` troca só o prefixo dos nomes, para cada tela manter a sua
 * caixa. Os ganchos de pintura (`data-hold`) são os mesmos em todas.
 */
export function barraHTML(rotulo, { classe = 'hold' } = {}) {
  return `
    <div class="${classe}__fill" data-hold="fill"></div>
    <div class="${classe}__label">${rotulo}</div>
    <div class="${classe}__label ${classe}__label--over"
         data-hold="clip" data-hold-over>${rotulo}</div>`;
}

const seg = (ms) =>
  (ms / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/**
 * Pintor padrão. Casa com `barraHTML` e com qualquer
 * `[data-hold="elapsed"]` que a tela tenha posto por perto — pode haver
 * mais de um quando o conteúdo é duplicado para o recorte.
 */
export function pintarBarra(host, t, ms = SEGURAR_MS) {
  if (!host) return;
  const avanco = (t * 100).toFixed(1);
  for (const el of host.querySelectorAll('[data-hold="fill"]')) {
    el.style.width = `${avanco}%`;
  }
  for (const el of host.querySelectorAll('[data-hold="clip"]')) {
    el.style.clipPath = `inset(0 ${(100 - t * 100).toFixed(1)}% 0 0)`;
  }
  for (const el of host.querySelectorAll('[data-hold="elapsed"]')) {
    el.textContent = `${seg(t * ms)} s DE ${seg(ms)} s`;
  }
}
