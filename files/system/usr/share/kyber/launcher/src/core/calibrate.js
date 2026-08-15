/* =====================================================================
   KYBER — instrumento de calibração de controle

   NÃO é uma das 19 telas e não tem entrada pela interface: abre só pelo
   console, com `kyber.calibrar()`. Existe porque confirmar o mapeamento
   XInput e afinar repeat e deadzone são medições que precisam do
   aparelho na mão e da TV na frente — e adivinhar valores no escuro é
   pior que medir.

   Não prende o foco de propósito: com ele aberto os botões continuam
   navegando o launcher, então dá para ver o índice cru e o efeito na
   interface ao mesmo tempo.
   ===================================================================== */

const NOMES = {
  0: 'A', 1: 'B', 2: 'X', 3: 'Y', 4: 'LB', 5: 'RB',
  6: 'LT', 7: 'RT', 8: 'VIEW', 9: 'MENU', 10: 'L3', 11: 'R3',
  12: 'D-PAD ↑', 13: 'D-PAD ↓', 14: 'D-PAD ←', 15: 'D-PAD →', 16: 'GUIDE',
};

/* Índices que a camada de input realmente consome. O resto aparece para
   diagnóstico, mas não move nada. */
const USADOS = new Set([0, 1, 2, 3, 4, 5, 12, 13, 14, 15, 16]);

let node = null;
let raf = 0;

export function calibrar(input, ligado = !node) {
  if (!ligado) {
    cancelAnimationFrame(raf);
    node?.remove();
    node = null;
    return 'calibração fechada';
  }
  if (node) return 'calibração já aberta';

  node = document.createElement('div');
  node.className = 'calib';
  node.innerHTML = `
    <div class="calib__head">
      <span data-calib="id">nenhum controle</span>
      <span data-calib="tune"></span>
    </div>
    <div class="calib__grid" data-calib="buttons"></div>
    <div class="calib__axes" data-calib="axes"></div>
    <div class="calib__foot">kyber.input.tune({ delay, rate, deadzone }) · kyber.calibrar(false)</div>`;
  document.getElementById('app').append(node);

  const dom = {
    id: node.querySelector('[data-calib="id"]'),
    tune: node.querySelector('[data-calib="tune"]'),
    buttons: node.querySelector('[data-calib="buttons"]'),
    axes: node.querySelector('[data-calib="axes"]'),
  };

  const cells = new Map();
  for (let i = 0; i <= 16; i++) {
    const cell = document.createElement('div');
    cell.className = `calib__btn${USADOS.has(i) ? '' : ' calib__btn--unused'}`;
    cell.innerHTML = `<span class="calib__idx">${String(i).padStart(2, '0')}</span>
                      <span class="calib__name">${NOMES[i] ?? '—'}</span>`;
    dom.buttons.append(cell);
    cells.set(i, cell);
  }

  const tick = () => {
    const pad = input.padIndex !== null ? navigator.getGamepads()[input.padIndex] : null;
    const t = input.tuning;
    dom.tune.textContent =
      `delay ${t.delay} ms · taxa ${t.rate} ms · deadzone ${t.deadzone} · guide ${t.guideHold} ms`;

    if (!pad) {
      dom.id.textContent = 'NENHUM CONTROLE · a camada está no teclado';
      dom.axes.textContent = '';
      cells.forEach((c) => { c.dataset.on = 'false'; });
    } else {
      dom.id.textContent =
        `${pad.id} · mapping ${pad.mapping || 'não padrão'} · ${pad.buttons.length} botões`;
      dom.id.dataset.warn = pad.mapping === 'standard' ? 'false' : 'true';
      cells.forEach((cell, i) => {
        cell.dataset.on = pad.buttons[i]?.pressed ? 'true' : 'false';
      });
      dom.axes.textContent = pad.axes
        .map((v, i) => `eixo ${i} ${v >= 0 ? ' ' : ''}${v.toFixed(3)}`)
        .join('   ');
    }
    raf = requestAnimationFrame(tick);
  };
  tick();

  return 'calibração aberta — pressione cada botão e leia o índice aceso';
}
