/* =====================================================================
   KYBER — teclado virtual

   COMPONENTE, não tela. Vive dentro de quem precisa dele — busca (13),
   login Steam (11) e senha de Wi-Fi (Rede) — e o D-pad atravessa a
   fronteira entre ele e o conteúdo sem fechá-lo. Por isso ele expõe uma
   região de foco (`data-region`) em vez de um trap: é a navegação
   espacial normal que leva de uma tecla para o conteúdo acima.

   Dois modos:
     inline   ancorado na metade inferior da tela, sem scrim. O conteúdo
              acima continua navegável e o campo espelhado é da tela.
     overlay  camada com scrim sobre a tela inteira, campo espelhado
              próprio no topo. É o caso da senha de Wi-Fi.

   Os botões físicos gravados nas teclas de ação funcionam de verdade
   enquanto o foco está no teclado: Ⓨ espaço, Ⓑ apaga, LB maiúscula,
   RB símbolos. Ⓑ aqui NÃO desempilha — quem consome é a tela.
   ===================================================================== */

import { glifoHTML } from '../core/glyphs.js';

const LETRAS = ['QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM-_'];
const NUMEROS = ['1234567890', '@#$%&*()', '.,;:!?/\\', '+=<>[]{}'];
const SIMBOLOS = ['1234567890', "áéíóúâêôãõç", '@#$%&*()_-', '.,;:!?/+='];

/* A gravação é o NOME DA FUNÇÃO; quem desenha é o módulo de glifos, para
   a tecla ESPAÇO gravar Ⓨ num Xbox e △ num DualSense sem mudar nada aqui. */
const ACOES = {
  shift:   { label: 'MAIÚSCULA', engraving: 'LB', width: 200 },
  numeros: { label: 'NÚMEROS',   engraving: 'RB', width: 200 },
  simbolos:{ label: 'SÍMBOLOS',  engraving: 'RB', width: 200 },
  espaco:  { label: 'ESPAÇO',    engraving: 'Y', width: null },
  apagar:  { label: 'APAGAR',    engraving: 'B', width: 220 },
  confirmar:{ label: 'CONFIRMAR', engraving: 'MENU', width: 260, primary: true },
};

/* Botão físico → ação, enquanto o foco está no teclado. */
const ATALHOS = { y: 'espaco', b: 'apagar', lb: 'shift', rb: 'simbolos' };

export function createKeyboard({
  /* O gerente de foco entra por parâmetro porque o teclado se
     reconstrói ao trocar de mapa: focar o nó novo direto no DOM deixaria
     o gerente apontando para um nó já removido, e a próxima seta cairia
     no vazio. */
  focus = null,
  mode = 'inline',
  region = 'keyboard',
  regionUp = null,
  actions = ['numeros', 'espaco', 'apagar'],
  hint = null,
  maxLength = 63,
  /* Em camada, o teclado é o alvo inicial. Ancorado, quem manda no foco
     inicial é o conteúdo da tela. */
  initialFocus = mode === 'overlay',
  value = '',
  onChange = () => {},
  onConfirm = () => {},
} = {}) {
  let texto = value;
  let maiuscula = false;
  let mapa = 'letras';

  const el = document.createElement('div');
  el.className = `kb kb--${mode}`;
  const teclas = document.createElement('div');
  teclas.className = 'kb__keys';
  teclas.dataset.region = region;
  teclas.dataset.regionFlow = 'grid';
  teclas.dataset.regionDim = 'off';
  if (regionUp) teclas.dataset.regionUp = regionUp;
  el.append(teclas);

  render();

  return {
    el,
    region,
    get value() { return texto; },
    set value(v) { texto = v; onChange(texto); },
    /** A tela chama isto ao receber um botão. Devolve true se consumiu. */
    handleAction,
    focusFirst: () => teclas.querySelector('[tabindex]'),
  };

  /* ---------- montagem ---------- */

  function linhas() {
    if (mapa === 'numeros') return NUMEROS;
    if (mapa === 'simbolos') return SIMBOLOS;
    return LETRAS;
  }

  function render() {
    /* Trocar de mapa reconstrói as teclas. Guarda o alvo por tecla OU por
       ação: sem isto, apertar NÚMEROS derruba o foco no vazio, porque a
       tecla que estava focada deixa de existir. */
    const anterior = document.activeElement;
    const marcado = teclas.contains(anterior)
      ? { key: anterior.dataset.key, action: anterior.dataset.action }
      : null;
    teclas.replaceChildren();

    for (const linha of linhas()) {
      const row = document.createElement('div');
      row.className = 'kb__row';
      for (const ch of linha) {
        const glyph = maiuscula ? ch.toUpperCase() : ch.toLowerCase();
        const key = document.createElement('div');
        key.className = 'kb__key focusable';
        key.tabIndex = 0;
        key.setAttribute('role', 'button');
        key.dataset.key = ch;
        key.textContent = /[a-záéíóúâêôãõç]/i.test(ch) ? glyph : ch;
        key.setAttribute('aria-label', key.textContent);
        row.append(key);
      }
      teclas.append(row);
    }

    if (initialFocus) teclas.querySelector('[tabindex]')?.setAttribute('data-focus-initial', '');

    const row = document.createElement('div');
    row.className = 'kb__row kb__row--actions';
    for (const id of actions) {
      const spec = ACOES[id];
      if (!spec) continue;
      const key = document.createElement('div');
      key.className = `kb__key kb__key--action focusable${spec.primary ? ' kb__key--primary' : ''}`;
      key.tabIndex = 0;
      key.setAttribute('role', 'button');
      key.dataset.action = id;
      if (spec.width) key.style.flex = `none`;
      if (spec.width) key.style.width = `${spec.width}px`;
      key.innerHTML =
        `<span class="kb__label"></span><span class="kb__engraving"></span>`;
      key.querySelector('.kb__label').textContent =
        id === 'shift' ? (maiuscula ? 'MINÚSCULA' : 'MAIÚSCULA')
        : id === 'simbolos' || id === 'numeros'
          ? (mapa === 'letras' ? spec.label : 'LETRAS')
          : spec.label;
      key.querySelector('.kb__engraving').innerHTML =
        spec.engraving === 'MENU' ? 'MENU' : glifoHTML(spec.engraving);
      key.setAttribute('aria-label', key.querySelector('.kb__label').textContent);
      row.append(key);
    }
    if (hint) {
      const cell = document.createElement('div');
      cell.className = 'kb__hint';
      cell.innerHTML = `<span class="kb__label"></span><span class="kb__engraving"></span>`;
      cell.querySelector('.kb__label').textContent = hint.label;
      cell.querySelector('.kb__engraving').textContent = hint.engraving;
      row.append(cell);
    }
    teclas.append(row);

    /* Re-render troca os nós: devolve o foco ao mesmo alvo. */
    if (marcado) {
      const seletor = marcado.action
        ? `[data-action="${marcado.action}"]`
        : marcado.key ? `[data-key="${CSS.escape(marcado.key)}"]` : null;
      const alvo = seletor && teclas.querySelector(seletor);
      const destino = alvo ?? teclas.querySelector('[tabindex]');
      if (destino) {
        if (focus) focus.focus(destino);
        else destino.focus({ preventScroll: true });
      }
    }
  }

  /* ---------- entrada ---------- */

  function handleAction(action) {
    const foco = document.activeElement;
    const dentro = teclas.contains(foco);

    if (action === 'a' && dentro) {
      if (foco.dataset.action) return acionar(foco.dataset.action);
      if (foco.dataset.key) return digitar(foco.textContent);
      return false;
    }

    /* Atalhos físicos só valem com o foco no teclado — fora dele, Ⓑ
       volta a ser voltar e Ⓨ volta a ser a ação contextual da tela. */
    if (dentro && ATALHOS[action]) return acionar(ATALHOS[action]);
    return false;
  }

  function acionar(id) {
    if (id === 'shift') { maiuscula = !maiuscula; render(); return true; }
    if (id === 'numeros' || id === 'simbolos') {
      mapa = mapa === 'letras' ? (id === 'numeros' ? 'numeros' : 'simbolos') : 'letras';
      render();
      return true;
    }
    if (id === 'espaco') return digitar(' ');
    if (id === 'apagar') {
      /* Sem nada para apagar, Ⓑ deixa de ser do teclado e volta a ser do
         sistema. Sem esta saída, quem digita algo que não casa com nada
         fica preso: a lista vazia não recebe o D-pad e o Ⓑ só apagava. */
      if (!texto) return false;
      texto = texto.slice(0, -1);
      onChange(texto);
      return true;
    }
    if (id === 'confirmar') { onConfirm(texto); return true; }
    return false;
  }

  function digitar(ch) {
    if (texto.length >= maxLength) return true;
    texto += ch;
    onChange(texto);
    return true;
  }
}
