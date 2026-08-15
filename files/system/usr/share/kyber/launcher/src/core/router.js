/* =====================================================================
   KYBER — router

   Pilha de telas, não histórico de browser. Ⓑ desempilha. Não há URL,
   não há voltar do navegador, não há tela alcançável por endereço: o
   único caminho é o que o usuário empilhou.

   A tela de baixo NÃO é destruída ao empilhar — ela fica montada e
   invisível. É isso que devolve o foco exatamente ao card de origem no
   retorno, junto com a rolagem da prateleira e a memória de região do
   focus.js. Reconstruir a tela ao voltar devolveria o topo da lista, que
   é o comportamento de site, não de console.

   `visibility: hidden` e não `display: none` justamente porque a caixa de
   layout precisa sobreviver: sem caixa, o navegador zera o scrollLeft da
   prateleira e a volta perde a posição.

   Escopo de foco: cada tela empilhada vira um trap do focus.js. É o que
   impede o foco de vazar para a tela de baixo, que continua no DOM, e é
   o que guarda o elemento de origem para o retorno.

   ---------------------------------------------------------------------
   Contrato de tela — o que uma fábrica de tela devolve:

     el         HTMLElement   raiz da tela; o router monta e desmonta
     overlay    boolean       true monta por cima do chrome e NÃO esconde
                              a tela de baixo — ela fica atrás do scrim
     chrome     'full'|'boot'|'bare'  quanto de chrome a tela quer.
                              Ausente = 'full'. Overlay não muda o modo:
                              o chrome que aparece atrás do scrim é o da
                              tela de baixo.
     onEnter()  opcional      declara nome, legendas e contexto do rodapé.
                              Chamado ao montar E ao voltar por cima dela.
     onLeave()  opcional      chamado ao sair, empilhando ou desempilhando
     onAction() opcional      recebe 'a' | 'x' | 'y' | 'lb' | 'rb' | …
     unmount()  opcional      destruição definitiva: timers, assinaturas
   ===================================================================== */

import { state } from './state.js';

export class Router {
  constructor({ mountPoint, overlayPoint = mountPoint, focus, context = {} }) {
    this.mountPoint = mountPoint;
    /* Overlay não é tela: monta por cima de TUDO, chrome inclusive. O
       scrim escurece header, régua e rodapé sem apagá-los — é assim que
       o overlay "herda a régua da tela por baixo". */
    this.overlayPoint = overlayPoint;
    this.focus = focus;
    this.stack = [];
    this.busy = false;
    /* Passado a toda fábrica de tela. O router se inclui para que uma
       tela possa empilhar outra sem conhecer o main, e inclui o
       focusManager porque é ele quem a tela usa para recolocar o foco
       depois de reconstruir a própria lista. */
    this.context = { ...context, router: this, focus };
  }

  get current() {
    return this.stack[this.stack.length - 1] ?? null;
  }

  get depth() {
    return this.stack.length;
  }

  /** Empilha uma tela por cima da atual. A de baixo continua montada. */
  async push(factory, ...args) {
    if (this.busy) return null;            // Ⓐ repetido não empilha duas vezes
    this.busy = true;
    try {
      const screen = await factory(this.context, ...args);

      const below = this.current;
      /* A tela de baixo de um overlay não sai de cena: ela continua
         visível atrás do scrim, e por isso não recebe onLeave nem some. */
      if (below && !screen.overlay) {
        below.onLeave?.();
        below.el.dataset.hidden = 'true';
      }

      (screen.overlay ? this.overlayPoint : this.mountPoint).append(screen.el);
      this.stack.push(screen);
      this._chrome(screen);
      screen.onEnter?.();
      this.focus.pushTrap(screen.el);
      return screen;
    } finally {
      this.busy = false;
    }
  }

  /** Quanto de chrome a tela quer. Overlay não mexe: o que aparece atrás
      do scrim é da tela de baixo, e trocar o modo faria o fundo piscar. */
  _chrome(screen) {
    if (screen.overlay) return;
    state.set('chromeMode', screen.chrome ?? 'full');
  }

  /** Ⓑ. Devolve false na raiz — não há o que desempilhar. */
  pop() {
    if (this.stack.length <= 1) return false;

    const top = this.stack.pop();
    top.onLeave?.();
    top.el.remove();
    top.unmount?.();

    /* Revelar antes de devolver o foco: o focus.js mede geometria, e
       elemento sem caixa visível não recebe foco. */
    const below = this.current;
    if (!top.overlay) delete below.el.dataset.hidden;
    this._chrome(below);
    below.onEnter?.();
    this.focus.popTrap();

    return true;
  }

  /** Esvazia a pilha e monta uma raiz nova. É o que o toque no Guide
      faz: "volta ao launcher" não é desempilhar um nível, é voltar ao
      começo, seja lá onde a pessoa estivesse. */
  async reset(factory, ...args) {
    if (this.busy) return null;
    this.busy = true;
    try {
      const screen = await factory(this.context, ...args);

      while (this.stack.length) {
        const s = this.stack.pop();
        s.onLeave?.();
        this.focus.popTrap();
        s.el.remove();
        s.unmount?.();
      }

      this.mountPoint.append(screen.el);
      this.stack.push(screen);
      this._chrome(screen);
      screen.onEnter?.();
      this.focus.pushTrap(screen.el);
      return screen;
    } finally {
      this.busy = false;
    }
  }

  /** Troca lateral, sem mexer na profundidade da pilha — vitrine ⇄ índice
      são a mesma altura da pilha, não uma dentro da outra. */
  async replace(factory, ...args) {
    if (this.busy) return null;
    this.busy = true;
    try {
      const screen = await factory(this.context, ...args);

      const old = this.stack.pop();
      if (old) {
        old.onLeave?.();
        this.focus.popTrap();
        old.el.remove();
        old.unmount?.();
      }

      this.mountPoint.append(screen.el);
      this.stack.push(screen);
      this._chrome(screen);
      screen.onEnter?.();
      this.focus.pushTrap(screen.el);
      return screen;
    } finally {
      this.busy = false;
    }
  }
}
