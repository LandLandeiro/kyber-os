/* =====================================================================
   KYBER — tela 10 · Armazenamento

   Lista o que ocupa o disco e abre um painel lateral por item. Ⓐ abre o
   painel; Ⓑ fecha o painel; Ⓑ de novo sai da tela.

   DESINSTALAR exige SEGURAR Ⓐ POR 2 s. Não é atrito decorativo: é a
   única ação desta tela que apaga dado do usuário, e um toque de Ⓐ é
   barato demais para isso. O botão mostra o tempo correndo e diz que
   soltar cancela — a pessoa vê a conta antes de ela fechar.
   ===================================================================== */

import { state } from '../core/state.js';
import { glifoHTML } from '../core/glyphs.js';
import { DataAdapter } from '../data/adapter.js';
import { generatedCover } from './cover.js';
import { gb, ultimoAcessoCurto, NIVEL, createNotice, sortGames } from './format.js';
import { toast } from '../core/toast.js';
import { criarSegurar, barraHTML, pintarBarra, SEGURAR_MS } from '../components/hold.js';

const HINTS_LISTA = [
  { glyph: 'A', label: 'ABRIR ITEM' },
  { glyph: 'B', label: 'VOLTAR' },
  { glyph: 'Y', label: 'VERIFICAR ARQUIVOS' },
];

const HINTS_PAINEL = [
  { glyph: 'A', label: 'SEGURAR PARA DESINSTALAR' },
  { glyph: 'B', label: 'FECHAR PAINEL' },
];

const VISIVEIS = 5;

export async function createStorage({ router, focus }) {
  const disk = await DataAdapter.storage();
  const jogos = sortGames(
    (await DataAdapter.listGames()).filter((g) => g.installed),
    'tamanho'
  );

  /* O contexto conta os títulos, e desinstalar muda a conta. */
  const contexto = () => `${jogos.length} TÍTULOS · MAIORES PRIMEIRO`;
  let notice = createNotice(contexto());

  const el = template(disk, jogos);
  const lista = el.querySelector('[data-region="items"]');
  const painelEl = el.querySelector('[data-storage="panel"]');

  let aberto = null;          /* appid do item com painel aberto */

  /* Mecânica compartilhada com o menu de energia: mesma pressão, mesma
     conta, mesmo cancelamento ao soltar. */
  const segurar = criarSegurar({
    onProgresso: (t) => pintarBarra(painelEl, t),
    onConcluir: concluir,
  });

  el.addEventListener('kyber:focus', (e) => {
    const row = e.target.closest('[data-appid]');
    if (row) state.set('selectedGame', Number(row.dataset.appid));
  });

  /* O segurar-Ⓐ mede a pressão, então precisa da descida e da subida —
     `kyber:action` sozinho só conta o toque. */
  const onPress = (e) => {
    const { action, down } = e.detail;
    if (action !== 'a') return;
    if (document.activeElement?.dataset?.storage !== 'uninstall') return;
    if (down) segurar.iniciar();
    else segurar.cancelar();
  };

  return { el, onEnter, onLeave, onAction, unmount };

  /* ---------- ciclo de vida ---------- */

  function onEnter() {
    state.set('screenName', 'ARMAZENAMENTO');
    state.set('hints', aberto ? HINTS_PAINEL : HINTS_LISTA);
    notice.restore();
    window.addEventListener('kyber:press', onPress);
  }

  function onLeave() {
    notice.stop();
    segurar.cancelar();
    window.removeEventListener('kyber:press', onPress);
  }

  function unmount() { onLeave(); }

  /* ---------- ações ---------- */

  function onAction(action) {
    if (action === 'b' && aberto !== null) { fecharPainel(); return true; }

    if (action === 'y') {
      notice('VERIFICAR ARQUIVOS · NÃO IMPLEMENTADO');
      return true;
    }

    if (action !== 'a') return undefined;

    const alvo = document.activeElement;
    if (alvo?.dataset?.storage === 'close') { fecharPainel(); return true; }
    if (alvo?.dataset?.storage === 'move') {
      notice('MOVER PARA HD EXTERNO · NÃO IMPLEMENTADO');
      return true;
    }
    /* O botão de desinstalar não responde ao toque: quem manda nele é o
       tempo de pressão, medido em kyber:press. */
    if (alvo?.dataset?.storage === 'uninstall') return true;

    const row = alvo?.closest?.('[data-appid]');
    if (row) { abrirPainel(Number(row.dataset.appid)); return true; }
    return undefined;
  }

  /* ---------- painel lateral ---------- */

  async function abrirPainel(appid) {
    const jogo = jogos.find((g) => g.appid === appid);
    if (!jogo) return;
    const detalhe = await DataAdapter.storageDetail(appid);
    aberto = appid;

    el.dataset.panel = 'true';
    painelEl.innerHTML = painelHtml(jogo, detalhe);
    painelEl.querySelector('[data-storage="cover"]').append(generatedCover(jogo, 'tile'));
    state.set('hints', HINTS_PAINEL);
    focus.pushTrap(painelEl);
  }

  function fecharPainel() {
    if (aberto === null) return;
    aberto = null;
    segurar.cancelar();
    el.dataset.panel = 'false';
    focus.popTrap();
    painelEl.replaceChildren();
    state.set('hints', HINTS_LISTA);
  }

  /* ---------- segurar Ⓐ ---------- */

  async function concluir() {
    const appid = aberto;
    /* A mecânica já parou sozinha ao chegar em 1; aqui só devolvemos a
       barra ao zero, para o painel não reabrir cheio. */
    pintarBarra(painelEl, 0);
    const jogo = jogos.find((g) => g.appid === appid);
    try {
      await DataAdapter.uninstall(appid);
      fecharPainel();
      const i = jogos.findIndex((g) => g.appid === appid);
      if (i >= 0) jogos.splice(i, 1);
      redesenharLista();
      notice = createNotice(contexto());
      notice.restore();
      toast({
        kind: 'info',
        title: 'TÍTULO DESINSTALADO',
        body: `${jogo.name} · ${gb(jogo.sizeGB)} liberados`,
      });
    } catch (erro) {
      toast({ kind: 'error', title: 'NÃO FOI POSSÍVEL DESINSTALAR', body: erro.message });
      fecharPainel();
    }
  }

  function redesenharLista() {
    lista.replaceChildren(...jogos.map(linha));
    const alvo = lista.firstElementChild;
    if (alvo) { alvo.setAttribute('data-focus-initial', ''); focus.focus(alvo); }
    el.querySelector('[data-storage="resumo"]').textContent = resumo(jogos);
  }
}

/* ---------- marcação ---------- */

function template(disk, jogos) {
  const section = document.createElement('section');
  section.className = 'storage screen__page';
  section.dataset.panel = 'false';

  const jogosGB = disk.gamesGB;
  const sistemaGB = disk.systemGB;
  const outrosGB = disk.otherGB;
  const livreGB = disk.totalGB - disk.usedGB;
  const pct = (v) => `${((v / disk.totalGB) * 100).toFixed(2)}%`;

  section.innerHTML = `
    <div class="disk">
      <div class="disk__head">
        <div>
          <div class="disk__label">NVME · SAMSUNG 990 PRO 1 TB</div>
          <div class="disk__used">${Math.round(disk.usedGB)}<span class="disk__unit"> / ${disk.totalGB} GB</span></div>
        </div>
        <div class="disk__free">
          <div class="disk__label">LIVRE</div>
          <div class="disk__free-value">${Math.round(livreGB)} GB</div>
        </div>
      </div>
      <div class="disk__sort">LB / RB ORDENAR: TAMANHO</div>
      <div class="bar">
        <div class="bar__seg bar__seg--games" style="width:${pct(jogosGB)}"></div>
        <div class="bar__seg bar__seg--system" style="width:${pct(sistemaGB)}"></div>
        <div class="bar__seg bar__seg--other" style="width:${pct(outrosGB)}"></div>
        <div class="bar__seg bar__seg--free"></div>
      </div>
      <div class="legend">
        ${[['games', 'JOGOS', jogosGB], ['system', 'SISTEMA', sistemaGB],
           ['other', 'OUTROS', outrosGB], ['free', 'LIVRE', livreGB]]
          .map(([k, l, v]) => `
            <div class="legend__item">
              <span class="legend__mark legend__mark--${k}"></span>
              <span class="legend__name">${l}</span>
              <span class="legend__value">${Math.round(v)} GB</span>
            </div>`).join('')}
      </div>
    </div>

    <div class="items">
      <div class="items__head">
        <div>Nº</div><div>TÍTULO</div>
        <div class="items__right">GB</div>
        <div class="items__right">ACESSO</div>
        <div class="items__right">PERFIL</div>
      </div>
      <div class="items__list" data-region="items" data-region-flow="vertical"
           data-region-dim="off"></div>
      <div class="items__rest texture">
        <span data-storage="resumo"></span>
        <span>D-PAD PARA CONTINUAR</span>
      </div>
    </div>

    <div class="storage__scrim"></div>
    <aside class="side" data-storage="panel"></aside>`;

  const lista = section.querySelector('[data-region="items"]');
  lista.append(...jogos.map(linha));
  lista.firstElementChild?.setAttribute('data-focus-initial', '');
  section.querySelector('[data-storage="resumo"]').textContent = resumo(jogos);
  return section;
}

function resumo(jogos) {
  const restantes = jogos.slice(VISIVEIS);
  if (!restantes.length) return 'FIM DA LISTA';
  const soma = restantes.reduce((s, g) => s + g.sizeGB, 0);
  const maior = Math.max(...restantes.map((g) => g.sizeGB));
  return `${restantes.length} TÍTULOS ABAIXO DE ${Math.ceil(maior)} GB · ${Math.round(soma)} GB SOMADOS`;
}

function linha(game) {
  const node = document.createElement('div');
  node.className = 'item row-invert';
  node.tabIndex = 0;
  node.setAttribute('role', 'button');
  node.setAttribute('aria-label', game.name);
  node.dataset.appid = game.appid;

  const est = DataAdapter.estimateProfile(game.profile);
  node.innerHTML = `
    <div class="item__thumb"></div>
    <div class="item__name">${escape(game.name)}</div>
    <div class="item__gb">${gb(game.sizeGB)}</div>
    <div class="item__access">${ultimoAcessoCurto(game.lastPlayed)}</div>
    <div class="item__profile">${NIVEL[est.level]}</div>`;
  node.querySelector('.item__thumb').append(generatedCover(game, 'tile'));
  return node;
}

function painelHtml(jogo, d) {
  return `
    <div class="side__head">
      <div class="side__kicker">
        <span>ITEM SELECIONADO</span><span>${jogo.catalog}</span>
      </div>
      <div class="side__id">
        <div class="side__cover" data-storage="cover"></div>
        <div>
          <div class="side__name">${escape(jogo.name)}</div>
          <div class="side__meta">${d.status}<br>PROTON ${d.proton.toUpperCase()}</div>
        </div>
      </div>
    </div>

    <div class="side__rows">
      ${[['Instalação', gb(d.installGB)], ['Shaders compilados', gb(d.shadersGB)],
         ['Saves locais', `${d.savesLocalMB} MB`], ['Saves na nuvem', d.cloud]]
        .map(([k, v]) => `
          <div class="side__row"><span>${k}</span><span>${v}</span></div>`).join('')}
    </div>

    <div class="side__foot">
      <p class="side__warn">Os saves na nuvem permanecem. Saves locais e shaders são apagados.</p>

      <div class="hold focusable" tabindex="0" role="button"
           data-storage="uninstall" data-focus-initial
           aria-label="Segure A para desinstalar">
        ${barraHTML(`SEGURE ${glifoHTML('A')} PARA DESINSTALAR`)}
      </div>
      <div class="hold__meta">
        <span data-hold="elapsed">0,0 s DE ${(SEGURAR_MS / 1000).toLocaleString('pt-BR', { minimumFractionDigits: 1 })} s</span>
        <span>SOLTE PARA CANCELAR</span>
      </div>

      <div class="side__actions">
        <div class="btn focusable" tabindex="0" role="button" data-storage="move">MOVER PARA HD EXTERNO</div>
        <div class="btn btn--quiet focusable" tabindex="0" role="button" data-storage="close">B</div>
      </div>
    </div>`;
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
