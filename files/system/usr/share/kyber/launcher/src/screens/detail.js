/* =====================================================================
   KYBER — tela 02 · Ficha do título

   Capa grande à esquerda, ficha à direita: metadados, painel de perfil
   de performance e as três ações.

   O painel de perfil é OPACO (`surface-1`). Não é escolha de gosto: a
   lei do vidro diz que só o que nós desenhamos pode ficar atrás dele, e
   painel de telemetria nunca é vidro — o rótulo secundário não passaria
   no contraste sobre uma capa clara.

   A capa aparece na proporção real, sem corte. Uma faixa de 850px de
   altura é larga demais para um retrato 2:3: encaixar a arte à força
   cortaria metade dela. O enquadramento com marcas de canto é o que
   transforma a folga em estrutura em vez de vazio.
   ===================================================================== */

import { state } from '../core/state.js';
import { DataAdapter } from '../data/adapter.js';
import { coverElement } from './cover.js';
import { createLaunch } from './launch.js';
import { createProfileEditor } from './profile-editor.js';
import { gb, horas, ultimoAcesso, NIVEL, DEGRAUS, createNotice } from './format.js';

const HINTS = [
  { glyph: 'A', label: 'SELECIONAR' },
  { glyph: 'B', label: 'VOLTAR' },
];

export async function createDetail({ router }, appid) {
  let game = await DataAdapter.getGame(appid);
  let est = DataAdapter.estimateProfile(game.profile);

  /* O contexto técnico da ficha é o comando real de lançamento. O
     produto tem orgulho do que roda por baixo. */
  const contextLine = `steam://rungameid/${game.appid}`;
  const notice = createNotice(contextLine);

  const el = template(game, est);

  const art = el.querySelector('[data-detail="art"]');
  const source = el.querySelector('[data-detail="source"]');
  const url = DataAdapter.coverUrl(game.appid, 'cover');
  const gerada = `${game.catalog} · CAPA GERADA`;
  art.append(coverElement(game, url, 'portrait', () => { source.textContent = gerada; }));
  source.textContent = url ? `${game.catalog} · ARTE DA LOJA` : gerada;

  return { el, onEnter, onLeave, onAction, unmount };

  async function onEnter() {
    state.set('screenName', 'FICHA DO TÍTULO');
    state.set('hints', HINTS);
    notice.restore();

    /* Relê o perfil a cada entrada: voltar do editor (04) tem que mostrar
       o que foi salvo, e a ficha não fica sabendo por outro caminho. */
    game = await DataAdapter.getGame(appid);
    est = DataAdapter.estimateProfile(game.profile);
    repintarPerfil();

    /* A régua prevê o perfil deste título — mesma proposta que a vitrine
       fazia com ele em foco, então entrar na ficha não move o cursor. */
    state.set('preview', { intensity: est.intensity, watts: est.watts });
  }

  /* Só o painel de perfil muda: nome, catálogo e capa são do título e
     não dependem do que o editor fez. */
  function repintarPerfil() {
    const celulas = el.querySelectorAll('.profile__value');
    const valores = [
      game.profile.governor, game.profile.gpuLevel,
      game.profile.fpsLimit, game.profile.priority,
    ];
    celulas.forEach((c, i) => { c.textContent = valores[i]; });

    el.querySelector('.profile__level-name').textContent = NIVEL[est.level];
    el.querySelectorAll('.profile__level .step').forEach((s, i) => {
      s.classList.toggle('step--on', i < DEGRAUS[est.level]);
    });
    el.querySelector('.profile__foot').textContent =
      `estimativa de ${est.watts} W · aplicado pelo gameprofiled no lançamento`;
  }

  function onLeave() { notice.stop(); }
  function unmount() { notice.stop(); }

  function onAction(action) {
    if (action !== 'a') return;
    const focused = document.activeElement?.dataset?.action;

    if (focused === 'back') { router.pop(); return; }

    if (focused === 'launch') { router.push(createLaunch, game.appid); return; }

    /* Tela 04 (editor de perfil) ainda não existe. Anunciar o que falta é
       a alternativa honesta a um botão que parece vivo. */
    if (focused === 'profile') { router.push(createProfileEditor, game.appid); return; }
    if (focused === 'achievements') notice('CONQUISTAS · NÃO IMPLEMENTADO');
  }
}

function template(game, est) {
  const section = document.createElement('section');
  section.className = 'detail screen__page';

  const meta = [game.catalog, game.year, game.genre, game.installed ? null : 'NÃO INSTALADO']
    .filter(Boolean)
    .join(' · ');

  const sub = game.hoursTotal
    ? `${horas(game.hoursTotal)} jogadas · ${ultimoAcesso(game.lastPlayed)} · ${gb(game.sizeGB)}`
    : `${ultimoAcesso(game.lastPlayed)} · ${gb(game.sizeGB)}`;

  /* Nível em três degraus de luminância. A rampa de estado fica na régua:
     o orçamento é de duas ocorrências saturadas por tela e o indicador de
     jogo vivo pode estar consumindo uma delas. */
  const steps = [1, 2, 3]
    .map((n) => `<span class="step${n <= DEGRAUS[est.level] ? ' step--on' : ''}"></span>`)
    .join('');

  const cell = (label, value) => `
    <div class="profile__cell">
      <div class="profile__label">${label}</div>
      <div class="profile__value">${value}</div>
    </div>`;

  section.innerHTML = `
    <div class="detail__frame">
      <div class="corner corner--tl"></div>
      <div class="corner corner--br"></div>
      <div class="detail__cover" data-detail="art"></div>
      <div class="detail__source" data-detail="source"></div>
    </div>

    <div class="detail__sheet">
      <div class="detail__meta">${meta}</div>
      <h1 class="detail__title">${escape(game.name)}</h1>
      <p class="detail__desc">${escape(game.summary)}</p>
      <div class="detail__sub">${sub}</div>

      <div class="profile">
        <div class="profile__head">
          <div class="profile__title">PERFIL DE PERFORMANCE</div>
          <div class="profile__level">
            <span class="steps">${steps}</span>
            <span class="profile__level-name">${NIVEL[est.level]}</span>
          </div>
        </div>
        <div class="profile__grid">
          ${cell('GOVERNOR', game.profile.governor)}
          ${cell('GPU', game.profile.gpuLevel)}
          ${cell('LIMITE DE FPS', game.profile.fpsLimit)}
          ${cell('PRIORIDADE', game.profile.priority)}
        </div>
        <div class="profile__foot">estimativa de ${est.watts} W · aplicado pelo gameprofiled no lançamento</div>
      </div>

      <!-- O dado de conquistas aparece na ficha e na tela 17 e não tem
           destino: a tela de conquistas é uma das quatro que o mapa
           prevê e ninguém desenhou. Fica alcançável e diz o que falta,
           em vez de ser um número que ignora quem aperta Ⓐ nele. -->
      <div class="achievements-region" data-region="sheet" data-region-flow="vertical"
           data-region-dim="off" data-region-down="actions">
      <div class="achievements row-invert" tabindex="0" role="button"
           data-action="achievements" aria-label="Conquistas">
        <span class="achievements__label">CONQUISTAS</span>
        <span class="achievements__value">22 / 40</span>
      </div>
      </div>

      <div class="actions" data-region="actions" data-region-flow="horizontal"
           data-region-dim="off" data-region-up="sheet">
        <div class="btn btn--primary focusable" tabindex="0" role="button"
             data-action="launch" data-focus-initial>JOGAR</div>
        <div class="btn focusable" tabindex="0" role="button"
             data-action="profile">EDITAR PERFIL</div>
        <div class="btn btn--quiet focusable" tabindex="0" role="button"
             data-action="back">VOLTAR</div>
      </div>
    </div>`;
  return section;
}

const escape = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
