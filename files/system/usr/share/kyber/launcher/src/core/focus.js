/**
 * KYBER — Navegação espacial por foco direcional.
 *
 * O documento de identidade visual registra o diagnóstico que define esta
 * arquitetura: "foco por geometria funciona por proximidade, não por grade
 * declarada; colunas irregulares vão produzir saltos inesperados; produção
 * precisa de vizinhança explícita por nó."
 *
 * Daí o modelo HÍBRIDO:
 *   1. Vizinho explícito (data-focus-left="#id") — sempre vence
 *   2. Geometria dentro da região atual
 *   3. Salto entre regiões, se a região permitir naquela direção
 *
 * REGIÕES existem porque a tela tem zonas com lógicas diferentes: a
 * prateleira rola na horizontal, a coluna de seções é vertical, o rodapé
 * não é navegável. Cada região lembra seu último foco (memória de região),
 * que é o comportamento esperado num console: voltar da ficha para a
 * biblioteca devolve o foco ao card de onde se saiu.
 *
 * Marcação esperada no HTML:
 *   <div data-region="shelf" data-region-flow="horizontal"
 *        data-region-up="hero" data-region-down="footer">
 *     <button class="focusable focusable--cover" tabindex="0">…</button>
 *   </div>
 */

const SELECTOR = '[tabindex]:not([tabindex="-1"]):not([disabled])';

export class FocusManager {
  constructor(root = document) {
    this.root = root;
    this.current = null;
    this.regionMemory = new Map();   // região → último elemento focado
    this.trapStack = [];             // pilha de overlays modais
  }

  /* ---------- ciclo de vida ---------- */

  /** Chamar depois de trocar de tela. Foca o alvo inicial da tela. */
  mount(screenEl) {
    const initial =
      screenEl.querySelector('[data-focus-initial]') ||
      screenEl.querySelector(SELECTOR);
    if (initial) this.focus(initial);
  }

  /** Overlay modal: enquanto houver trap, foco não escapa do elemento. */
  pushTrap(el) {
    this.trapStack.push({ el, restore: this.current });
    this.mount(el);
  }

  popTrap() {
    const t = this.trapStack.pop();
    if (t?.restore?.isConnected) this.focus(t.restore);
  }

  get scope() {
    return this.trapStack.length
      ? this.trapStack[this.trapStack.length - 1].el
      : this.root;
  }

  /* ---------- foco ---------- */

  focus(el) {
    if (!el) return;
    this.current = el;
    el.focus({ preventScroll: true });

    const region = el.closest('[data-region]');
    if (region) {
      this.regionMemory.set(region.dataset.region, el);
      this._dimSiblings(region, el);
      this._scrollIntoRegion(region, el);
    }
    el.dispatchEvent(new CustomEvent('kyber:focus', { bubbles: true }));
  }

  /** Irmãos do focado caem para .70 (identidade visual, seção 5). */
  _dimSiblings(region, el) {
    if (region.dataset.regionDim === 'off') return;
    region.querySelectorAll(SELECTOR).forEach((sib) => {
      sib.classList.toggle('focus-sibling-dim', sib !== el);
    });
  }

  /** Rolagem da prateleira/lista sem barra de scroll visível. */
  _scrollIntoRegion(region, el) {
    const flow = region.dataset.regionFlow || 'vertical';
    const r = el.getBoundingClientRect();
    const c = region.getBoundingClientRect();
    if (flow === 'horizontal') {
      if (r.left < c.left + 48) region.scrollLeft += r.left - c.left - 48;
      else if (r.right > c.right - 48) region.scrollLeft += r.right - c.right + 48;
    } else {
      if (r.top < c.top + 24) region.scrollTop += r.top - c.top - 24;
      else if (r.bottom > c.bottom - 24) region.scrollTop += r.bottom - c.bottom + 24;
    }
  }

  /* ---------- movimento direcional ---------- */

  move(dir) {
    if (!this.current) {
      this.mount(this.scope);
      return;
    }

    // 1. vizinho explícito vence sempre
    const explicit = this.current.dataset[`focus${cap(dir)}`];
    if (explicit) {
      const target = this.scope.querySelector(explicit);
      if (target) return this.focus(target);
    }

    const region = this.current.closest('[data-region]');

    // 2. geometria dentro da região
    if (region) {
      const inside = this._nearest(
        this.current,
        [...region.querySelectorAll(SELECTOR)],
        dir
      );
      if (inside) return this.focus(inside);

      // 3. salto entre regiões
      const nextName = region.dataset[`region${cap(dir)}`];
      if (nextName) {
        const next = this.scope.querySelector(`[data-region="${nextName}"]`);
        if (next) {
          const remembered = this.regionMemory.get(nextName);
          const target =
            remembered?.isConnected
              ? remembered
              : this._nearest(this.current, [...next.querySelectorAll(SELECTOR)], dir, true) ||
                next.querySelector(SELECTOR);
          if (target) return this.focus(target);
        }
      }
      return; // região fechada nessa direção: foco não se move
    }

    // sem região declarada: geometria global no escopo
    const anywhere = this._nearest(
      this.current,
      [...this.scope.querySelectorAll(SELECTOR)],
      dir
    );
    if (anywhere) this.focus(anywhere);
  }

  /**
   * Escolhe o candidato na direção pedida.
   * Custo = distância no eixo primário + desalinhamento no eixo secundário
   * com peso 2. O peso existe porque, num grid, o candidato "à direita mas
   * três linhas abaixo" é geometricamente próximo e semanticamente errado.
   */
  _nearest(from, candidates, dir, crossRegion = false) {
    const a = center(from);
    let best = null;
    let bestCost = Infinity;

    for (const el of candidates) {
      if (el === from) continue;
      const b = center(el);
      const dx = b.x - a.x;
      const dy = b.y - a.y;

      let primary, secondary;
      if (dir === 'left')       { primary = -dx; secondary = Math.abs(dy); }
      else if (dir === 'right') { primary =  dx; secondary = Math.abs(dy); }
      else if (dir === 'up')    { primary = -dy; secondary = Math.abs(dx); }
      else                      { primary =  dy; secondary = Math.abs(dx); }

      if (primary <= 1) continue;                       // não está na direção
      if (!crossRegion && secondary > primary * 2 + 80) continue; // ângulo absurdo

      const cost = primary + secondary * 2;
      if (cost < bestCost) { bestCost = cost; best = el; }
    }
    return best;
  }
}

const center = (el) => {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
};

const cap = (s) => s[0].toUpperCase() + s.slice(1);
