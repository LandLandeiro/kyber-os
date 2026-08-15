/* =====================================================================
   KYBER — tela 14 · Atualização do sistema

   Dois estados no mesmo arquivo: baixando (14) e pronta (14b). A troca
   não é botão nenhum — é o download chegando ao fim, lido do relógio do
   adapter, como um daemon de verdade seria lido.

   O tom aqui é segurança. A imagem é atômica: nada muda enquanto ela
   baixa, nada muda quando ela termina, e uma imagem que falhe volta
   sozinha no reboot seguinte. A tela diz isso em vez de pedir cautela.
   ===================================================================== */

import { state } from '../core/state.js';
import { glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';
import { gb, createNotice } from './format.js';
import { toast } from '../core/toast.js';
import { createLoader } from '../components/loader.js';

const HINTS = [
  { glyph: 'A', label: 'CONFIRMAR' },
  { glyph: 'B', label: 'VOLTAR' },
];

const POLL_MS = 500;

export async function createUpdate({ router, focus }) {
  let dados = await DataAdapter.systemUpdate();
  const notice = createNotice(
    `KYBER OS · ${dados.current.version} → ${dados.incoming.version}`
  );

  const el = document.createElement('section');
  el.className = 'update screen__page';

  let estadoDesenhado = null;
  let timer = 0;

  render();

  return { el, onEnter, onLeave, onAction, unmount };

  /* ---------- ciclo de vida ---------- */

  function onEnter() {
    state.set('screenName', 'ATUALIZAÇÃO DO SISTEMA');
    state.set('hints', HINTS);
    notice.restore();
    poll();
  }

  function onLeave() { notice.stop(); clearInterval(timer); }
  function unmount() { onLeave(); }

  /* Lê o daemon de meio em meio segundo. O que se move na tela é o
     progresso real do download, não uma animação decorativa. */
  function poll() {
    clearInterval(timer);
    timer = setInterval(async () => {
      dados = await DataAdapter.systemUpdate();
      if (dados.incoming.state !== estadoDesenhado) render();
      else atualizarNumeros();
    }, POLL_MS);
  }

  /* ---------- ações ---------- */

  function onAction(action) {
    if (action !== 'a') return undefined;
    const alvo = document.activeElement?.dataset?.update;
    if (!alvo) return undefined;

    if (alvo === 'pause' || alvo === 'resume') {
      DataAdapter.updateAction(alvo).then(async () => {
        dados = await DataAdapter.systemUpdate();
        render();
      });
      return true;
    }
    if (alvo === 'reboot') {
      notice('REINICIAR AGORA · SPLASH DE BOOT NÃO IMPLEMENTADO');
      return true;
    }
    if (alvo === 'defer') {
      router.pop();
      toast({
        kind: 'device',
        title: 'ATUALIZAÇÃO ADIADA',
        body: `${dados.incoming.version} entra no próximo boot · nada muda agora`,
      });
      return true;
    }
    /* Linha de geração: escolher a imagem do próximo boot é da tela 14
       completa, que não existe. */
    if (alvo === 'generation') {
      notice('ESCOLHER GERAÇÃO · NÃO IMPLEMENTADO');
      return true;
    }
    return undefined;
  }

  /* ---------- desenho ---------- */

  function render() {
    estadoDesenhado = dados.incoming.state;
    el.innerHTML = estadoDesenhado === 'PRONTA' ? pronta(dados) : baixando(dados);
    /* Verificação e download são esperas longas: varredura nos dois. */
    if (dados.incoming.state === 'BAIXANDO') {
      el.querySelector('[data-update="loader"]')?.append(createLoader('varredura', 26));
    }
    if (!el.querySelector('[data-focus-initial]')) {
      el.querySelector('[tabindex]')?.setAttribute('data-focus-initial', '');
    }
    if (el.isConnected) focus.mount(el);
  }

  /* Só os números, para o polling não reconstruir o DOM a cada 500ms e
     derrubar o foco de quem está lendo o changelog. */
  function atualizarNumeros() {
    const { doneGB, totalGB, speedMB, etaSeconds } = dados.incoming;
    const barra = el.querySelector('[data-update="bar"]');
    if (barra) barra.style.width = `${((doneGB / totalGB) * 100).toFixed(1)}%`;

    const medida = el.querySelector('[data-update="measure"]');
    if (medida) {
      medida.innerHTML =
        `<span class="update__done">${gb(doneGB)}</span> de ${gb(totalGB)} · ${speedMB} MB/s`;
    }
    const eta = el.querySelector('[data-update="eta"]');
    if (eta) eta.textContent = etaSeconds === null ? 'PAUSADO' : `RESTAM ${tempo(etaSeconds)}`;
  }
}

const tempo = (s) =>
  s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`;

/* ---------- 14 · baixando ---------- */

function baixando(d) {
  const { current, incoming, changelog } = d;
  const pct = ((incoming.doneGB / incoming.totalGB) * 100).toFixed(1);
  const pausado = incoming.state === 'PAUSADO';

  return `
    <div class="update__head">
      <h1 class="update__title">Atualização</h1>
      <span class="update__note">ATUALIZAÇÃO ATÔMICA</span>
    </div>

    <div class="image-card">
      <div class="image-card__top">
        <div>
          <div class="image-card__label">IMAGEM EM USO</div>
          <div class="image-card__version">KYBER OS · ${current.version}</div>
          <div class="image-card__base">base ${current.base} · kernel ${current.kernel}</div>
        </div>
        <div class="image-card__incoming">
          <div class="image-card__label image-card__label--vivo"><span data-update="loader"></span>${incoming.state}</div>
          <div class="image-card__next">${incoming.version}</div>
        </div>
      </div>

      <div class="update__bar">
        <div class="update__fill" data-update="bar" style="width:${pct}%"></div>
        <div class="update__ticks"></div>
      </div>

      <div class="update__measures">
        <span data-update="measure"><span class="update__done">${gb(incoming.doneGB)}</span> de ${gb(incoming.totalGB)} · ${incoming.speedMB} MB/s</span>
        <span data-update="eta">${incoming.etaSeconds === null ? 'PAUSADO' : `RESTAM ${tempo(incoming.etaSeconds)}`}</span>
      </div>

      <div class="update__seal">APLICA NO PRÓXIMO BOOT · ROLLBACK DISPONÍVEL</div>
    </div>

    <div class="update__section">
      <span>NOVIDADES DESTA IMAGEM</span>
      <span>D-PAD ↓ ROLA · ${changelog.length} LINHAS</span>
    </div>

    <div class="changelog" data-region="changelog" data-region-flow="vertical"
         data-region-dim="off" data-region-down="update-actions">
      ${changelog.map((l) => `
        <div class="changelog__line row-invert${l.minor ? ' changelog__line--minor' : ''}"
             tabindex="0" aria-label="${escape(l.text)}">
          <span class="changelog__version">${l.version}</span>
          <span class="changelog__text">${escape(l.text)}</span>
        </div>`).join('')}
    </div>

    <div class="update__actions" data-region="update-actions"
         data-region-flow="horizontal" data-region-dim="off"
         data-region-up="changelog">
      <div class="btn btn--primary focusable" tabindex="0" role="button"
           data-update="${pausado ? 'resume' : 'pause'}" data-focus-initial>${pausado ? 'RETOMAR' : 'PAUSAR'}</div>
      <div class="update__assurance">Nada é alterado enquanto baixa. A imagem em uso continua intacta no disco.</div>
    </div>`;
}

/* ---------- 14b · pronta ---------- */

function pronta(d) {
  const { current, incoming, generations } = d;

  return `
    <div class="update__head">
      <h1 class="update__title">Atualização</h1>
      <span class="update__note">ATUALIZAÇÃO ATÔMICA</span>
    </div>

    <div class="image-card">
      <div class="verified">
        <span class="verified__mark"></span>
        <span class="verified__text">IMAGEM BAIXADA E VERIFICADA</span>
      </div>
      <div class="versions">
        <div class="versions__cell">
          <div class="image-card__label">EM USO AGORA</div>
          <div class="versions__value versions__value--muted">${current.version}</div>
          <div class="versions__sub">base ${current.base}</div>
        </div>
        <div class="versions__cell">
          <div class="image-card__label">NO PRÓXIMO BOOT</div>
          <div class="versions__value">${incoming.version}</div>
          <div class="versions__sub">${gb(incoming.totalGB)} · assinatura conferida</div>
        </div>
      </div>
    </div>

    <div class="update__section">
      <span>GERAÇÕES NO DISCO</span>
      <span>${glifoHTML('A')} ESCOLHER PARA O PRÓXIMO BOOT</span>
    </div>

    <div class="generations" data-region="generations" data-region-flow="vertical"
         data-region-dim="off" data-region-down="update-actions">
      ${generations.map((g, i) => `
        <div class="generation row-invert" tabindex="0" role="button"
             data-update="generation" data-version="${g.version}"
             ${i === 0 ? 'data-focus-initial' : ''} aria-label="${g.version}">
          <span class="generation__version">${g.version}</span>
          <span class="generation__when">${g.when}</span>
          <span class="generation__role">${g.role}</span>
        </div>`).join('')}
    </div>

    <div class="update__actions" data-region="update-actions"
         data-region-flow="horizontal" data-region-dim="off"
         data-region-up="generations">
      <div class="btn btn--primary focusable" tabindex="0" role="button"
           data-update="reboot">REINICIAR AGORA</div>
      <div class="btn focusable" tabindex="0" role="button"
           data-update="defer">DEPOIS</div>
      <div class="update__assurance">Nada foi alterado no sistema em uso. Se a nova imagem falhar, o console volta para ${current.version} no reboot seguinte.</div>
    </div>`;
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
