/**
 * KYBER — Camada de input.
 *
 * Traduz teclado e Gamepad API para os MESMOS eventos semânticos, de modo que
 * nenhuma tela saiba de onde veio o comando. Teclado e controle são cidadãos
 * de igual peso (o pareamento, tela 16a, depende disso: sem controle pareado,
 * só o teclado navega).
 *
 * Eventos emitidos em window:
 *   kyber:move    { dir: 'up'|'down'|'left'|'right' }
 *   kyber:action  { action: 'a'|'b'|'x'|'y'|'lb'|'rb'|'guide'|'guide-hold' }
 *   kyber:pad     { connected, index, id, mapping, count, standard }
 *   kyber:press   { action, down }  — descida e subida de botão, para
 *                 controles que medem tempo de pressão (segurar Ⓐ por 2 s
 *                 na tela 10). `kyber:action` continua saindo na descida.
 *
 * Mapeamento de teclado:
 *   setas → move · Enter → a · Esc → b · f → x · e → y
 *   q/w → lb/rb · Tab → guide · Shift+Tab → guide-hold
 */

const KEY_MAP = {
  ArrowUp: ['move', 'up'],       ArrowDown:  ['move', 'down'],
  ArrowLeft: ['move', 'left'],   ArrowRight: ['move', 'right'],
  Enter: ['action', 'a'],        Escape: ['action', 'b'],
  f: ['action', 'x'],            e: ['action', 'y'],
  q: ['action', 'lb'],           w: ['action', 'rb'],
};

/* Padrão Xbox/XInput. Estes índices são o "Standard Gamepad" do W3C, que
   é o que o Chrome entrega quando `gamepad.mapping === 'standard'` — e é
   o caso de Xbox, DualSense, 8BitDo em modo X e Switch Pro no macOS.
   Fora do modo standard os índices não são confiáveis e a camada avisa em
   vez de adivinhar: ver `standard` no evento kyber:pad. */
const PAD_BUTTONS = {
  0: 'a', 1: 'b', 2: 'x', 3: 'y',
  4: 'lb', 5: 'rb', 16: 'guide',
  12: 'up', 13: 'down', 14: 'left', 15: 'right',
};

/* Ponto de partida da calibração, não verdade revelada. Ajustável em
   tempo de execução por `input.tune()` para que a aferição na TV não
   dependa de editar arquivo e recarregar. */
const DEFAULTS = {
  delay: 420,      /* espera antes de repetir ao segurar */
  rate: 110,       /* intervalo do repeat */
  deadzone: 0.55,  /* drift de analógico movendo foco sozinho é inaceitável */
  guideHold: 650,  /* segurar Guide abre o menu de energia */
};

export class InputManager {
  constructor(tuning = {}) {
    this.held = new Map();      /* botão → timestamp do último disparo */
    this.guideDownAt = 0;
    this.padIndex = null;
    this.pads = new Map();      /* índice → { id, mapping } */
    this.tuning = { ...DEFAULTS, ...tuning };
    this._loop = this._loop.bind(this);
  }

  /** Calibração em tempo de execução. `kyber.input.tune({ rate: 90 })`. */
  tune(next = {}) {
    Object.assign(this.tuning, next);
    return { ...this.tuning };
  }

  get padCount() { return this.pads.size; }

  /** Controle que está dirigindo a navegação agora. */
  get activePad() {
    return this.padIndex === null ? null : this.pads.get(this.padIndex) ?? null;
  }

  start() {
    window.addEventListener('keydown', (e) => this._onKey(e));
    window.addEventListener('keyup', (e) => this._onKeyUp(e));

    window.addEventListener('gamepadconnected', (e) => {
      const { index, id, mapping } = e.gamepad;
      this.pads.set(index, { id, mapping });

      /* O último a chegar dirige — mas só se der para confiar nos
         índices dele. Entregar a navegação a um controle fora do padrão
         trocaria Ⓐ por Ⓑ sem aviso; melhor manter quem já funcionava. */
      const confiavel = mapping === 'standard';
      if (confiavel || this.padIndex === null) this.padIndex = index;
      emit('kyber:pad', {
        connected: true, index, id, mapping,
        standard: mapping === 'standard',
        count: this.pads.size,
      });
    });

    window.addEventListener('gamepaddisconnected', (e) => {
      const { index, id } = e.gamepad;
      this.pads.delete(index);
      /* Sobrou outro? Ele assume. Senão, volta para o teclado. */
      /* Ao sair o que dirigia, prefere um padrão entre os que ficaram. */
      const restantes = [...this.pads.entries()];
      const padrao = restantes.find(([, p]) => p.mapping === 'standard');
      this.padIndex = restantes.length ? (padrao ?? restantes.at(-1))[0] : null;
      this.held.clear();
      this.guideDownAt = 0;
      emit('kyber:pad', {
        connected: false, index, id,
        standard: true,
        count: this.pads.size,
      });
    });

    /* Controles já pareados antes do carregamento não disparam o evento
       de conexão até o primeiro botão; varrer aqui evita o launcher
       abrir achando que não há controle nenhum. */
    this._scan();

    requestAnimationFrame(this._loop);
  }

  _scan() {
    for (const pad of navigator.getGamepads?.() ?? []) {
      if (!pad || this.pads.has(pad.index)) continue;
      this.pads.set(pad.index, { id: pad.id, mapping: pad.mapping });
      this.padIndex = pad.index;
      emit('kyber:pad', {
        connected: true, index: pad.index, id: pad.id, mapping: pad.mapping,
        standard: pad.mapping === 'standard', count: this.pads.size, restored: true,
      });
    }
  }

  _onKey(e) {
    if (e.key === 'Tab') {                 /* Tab é o Guide no teclado */
      e.preventDefault();
      emit('kyber:action', { action: e.shiftKey ? 'guide-hold' : 'guide' });
      return;
    }
    const hit = KEY_MAP[e.key];
    if (!hit) return;
    e.preventDefault();
    const [kind, value] = hit;
    if (kind === 'move') { emit('kyber:move', { dir: value }); return; }

    /* Repetição do teclado não é uma nova pressão: quem mede tempo de
       pressão precisa de UMA descida por toque. */
    if (!e.repeat) emit('kyber:press', { action: value, down: true });
    emit('kyber:action', { action: value });
  }

  _onKeyUp(e) {
    const hit = KEY_MAP[e.key];
    if (!hit || hit[0] === 'move') return;
    emit('kyber:press', { action: hit[1], down: false });
  }

  _loop() {
    const pad = this.padIndex !== null ? navigator.getGamepads()[this.padIndex] : null;
    if (pad) {
      const now = performance.now();

      pad.buttons.forEach((btn, i) => {
        const name = PAD_BUTTONS[i];
        if (!name) return;

        if (btn.pressed) {
          /* Guide tem dois comportamentos: toque volta ao launcher,
             segurar abre o menu de energia (mapa de navegação, fase 3). */
          if (name === 'guide') {
            if (!this.guideDownAt) this.guideDownAt = now;
            else if (now - this.guideDownAt > this.tuning.guideHold && !this.held.has('guide-hold')) {
              this.held.set('guide-hold', now);
              emit('kyber:action', { action: 'guide-hold' });
            }
            return;
          }
          this._press(name, now, isDir(name));
        } else {
          if (name === 'guide' && this.guideDownAt) {
            if (!this.held.has('guide-hold')) emit('kyber:action', { action: 'guide' });
            this.guideDownAt = 0;
            this.held.delete('guide-hold');
          }
          /* Soltar precisa limpar TAMBÉM a marca de repetição. Sem isso
             o segundo toque no mesmo botão já entra repetindo a 110ms,
             pulando a espera de 420ms — a lista dispara sozinha na
             segunda vez que se segura o D-pad. */
          if (this.held.has(name)) emit('kyber:press', { action: name, down: false });
          this.held.delete(name);
          this.held.delete(`${name}:repeating`);
        }
      });

      /* Analógico esquerdo espelha o D-pad, com deadzone alta:
         em 10-foot UI, drift de analógico movendo foco sozinho é inaceitável. */
      const [ax, ay] = [pad.axes[0] ?? 0, pad.axes[1] ?? 0];
      if (Math.abs(ax) > this.tuning.deadzone || Math.abs(ay) > this.tuning.deadzone) {
        const dir = Math.abs(ax) > Math.abs(ay)
          ? (ax > 0 ? 'right' : 'left')
          : (ay > 0 ? 'down' : 'up');
        this._press(`axis:${dir}`, now, true, dir);
      } else {
        [...this.held.keys()].filter((k) => k.startsWith('axis:'))
          .forEach((k) => this.held.delete(k));
      }
    }
    requestAnimationFrame(this._loop);
  }

  _press(key, now, repeatable, dirOverride) {
    const last = this.held.get(key);
    const dir = dirOverride || key;

    if (last === undefined) {
      this.held.set(key, now);
      if (!key.startsWith('axis:')) emit('kyber:press', { action: key, down: true });
      this._fire(dir);
      return;
    }
    if (!repeatable) return;

    const elapsed = now - last;
    const threshold = this.held.get(`${key}:repeating`)
      ? this.tuning.rate
      : this.tuning.delay;
    if (elapsed > threshold) {
      this.held.set(key, now);
      this.held.set(`${key}:repeating`, true);
      this._fire(dir);
    }
  }

  _fire(name) {
    if (isDir(name)) emit('kyber:move', { dir: name });
    else emit('kyber:action', { action: name });
  }
}

const isDir = (n) => ['up', 'down', 'left', 'right'].includes(n);
const emit  = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));
