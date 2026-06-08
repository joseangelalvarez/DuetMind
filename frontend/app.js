const baseUrlInput = document.getElementById('baseUrl');
const healthStatus = document.getElementById('healthStatus');
const intentInput = document.getElementById('intent');
const agentMode = document.getElementById('agentMode');
const liveReasoning = document.getElementById('liveReasoning');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const phaseFeed = document.getElementById('phaseFeed');
const decisionBadge = document.getElementById('decisionBadge');
const decision = document.getElementById('decision');
const nextAction = document.getElementById('nextAction');
const plainExplanation = document.getElementById('plainExplanation');
const bundleSummary = document.getElementById('bundleSummary');
const runAllButton = document.getElementById('btnRunAll');

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function renderPhaseFeed(rows) {
  const recentRows = rows.slice(-6);
  phaseFeed.innerHTML = '';
  for (const row of recentRows) {
    const item = document.createElement('li');
    const title = document.createElement('strong');
    title.textContent = `Fase ${row.phase_id}`;
    item.appendChild(title);
    item.append(`: ${row.signal} (${row.reason})`);
    phaseFeed.appendChild(item);
  }
  if (recentRows.length === 0) {
    const item = document.createElement('li');
    item.textContent = 'Sin eventos nuevos por ahora.';
    phaseFeed.appendChild(item);
  }
}

function renderDecisionBadge(decisionValue, finalSignal) {
  decisionBadge.className = 'decision-badge';
  if (decisionValue === 'GO') {
    decisionBadge.classList.add('decision-go');
    decisionBadge.textContent = 'VERDE - GO';
    return;
  }
  if (decisionValue === 'GO_CONDICIONAL') {
    decisionBadge.classList.add('decision-conditional');
    decisionBadge.textContent = 'AMARILLO - GO_CONDICIONAL';
    return;
  }
  if (decisionValue === 'NO_GO') {
    decisionBadge.classList.add('decision-no-go');
    decisionBadge.textContent = finalSignal === 'ESCALAR_A_HUMANO' ? 'ROJO - ESCALAR_A_HUMANO' : 'ROJO - NO_GO';
    return;
  }
  decisionBadge.classList.add('decision-unknown');
  decisionBadge.textContent = 'Sin evaluar';
}

function buildPlainExplanation(goNoGo, bundle) {
  const reasons = Array.isArray(goNoGo.reasons) ? goNoGo.reasons : [];
  const completed = (bundle.phase_results || []).length;
  const blockers = (goNoGo.blocking_signals || []).length;
  const coverage = typeof goNoGo.coverage === 'number' ? Math.round(goNoGo.coverage * 100) : 0;

  if (goNoGo.decision === 'GO') {
    return 'Resultado favorable: el sistema completo todas las fases necesarias y no detecto bloqueos criticos. Puedes avanzar con confianza al siguiente objetivo.';
  }

  if (goNoGo.decision === 'GO_CONDICIONAL') {
    return `Resultado intermedio: el analisis avanza, pero conviene revisar detalles antes de continuar. Cobertura aproximada: ${coverage}% con ${completed} fases registradas.`;
  }

  const reasonHints = [];
  if (reasons.includes('blocking_signal_detected')) {
    reasonHints.push('aparecieron señales de bloqueo que requieren revisión');
  }
  if (reasons.includes('incomplete_phase_coverage')) {
    reasonHints.push('no se completaron todas las fases esperadas');
  }
  if (reasons.includes('average_score_below_threshold') || reasons.includes('minimum_score_below_threshold')) {
    reasonHints.push('la calidad promedio quedó por debajo del umbral configurado');
  }

  const details = reasonHints.length > 0 ? reasonHints.join('; ') : 'los indicadores de calidad no fueron suficientes para aprobar';
  return `Resultado no apto para avanzar automaticamente: ${details}. Se registraron ${completed} fases y ${blockers} bloqueos en esta corrida.`;
}

function startRunAllLivePolling(base, baselineHistoryCount) {
  const state = { active: true };

  const poll = async () => {
    if (!state.active) {
      return;
    }
    try {
      const history = await getJson(`${base}/history`);
      const rows = Array.isArray(history) ? history : [];
      const newRows = rows.slice(baselineHistoryCount);
      const completed = newRows.length;
      const percent = Math.min(100, Math.round((completed / 12) * 100));

      progressBar.style.width = `${percent}%`;
      progressText.textContent = `Progreso: ${Math.min(completed, 12)}/12 fases`;
      renderPhaseFeed(newRows);

      if (completed > 0) {
        const last = newRows[newRows.length - 1];
        liveReasoning.textContent = `Avance: fase ${last.phase_id} termino con ${last.signal}.`;
      } else {
        liveReasoning.textContent = 'Procesando run-all, esperando primeros resultados...';
      }
    } catch (_err) {
      liveReasoning.textContent = 'Ejecucion en curso; no se pudo leer progreso temporalmente.';
    }
  };

  const timer = setInterval(poll, 1400);
  poll();

  return {
    stop() {
      state.active = false;
      clearInterval(timer);
    },
  };
}

document.getElementById('btnHealth').addEventListener('click', async () => {
  const base = baseUrlInput.value.trim();
  healthStatus.textContent = 'Comprobando servidor...';
  try {
    const health = await getJson(`${base}/health`);
    healthStatus.textContent = health.status === 'ok' ? 'Servidor conectado y listo.' : 'Servidor responde pero no esta listo.';
  } catch (err) {
    healthStatus.textContent = `No se pudo conectar: ${err.message}`;
  }
});

document.getElementById('btnRunAll').addEventListener('click', async () => {
  const base = baseUrlInput.value.trim();
  const intent = intentInput.value.trim();
  const mode = agentMode.value;

  runAllButton.disabled = true;
  progressBar.style.width = '0%';
  progressText.textContent = 'Progreso: 0/12 fases';
  phaseFeed.innerHTML = '';
  decisionBadge.className = 'decision-badge decision-unknown';
  decisionBadge.textContent = 'En ejecucion';
  plainExplanation.textContent = 'Procesando resultados para explicacion no tecnica...';
  liveReasoning.textContent = 'Paso 1/4: iniciando run-all y monitoreo en vivo...';

  let baselineHistoryCount = 0;
  try {
    const history = await getJson(`${base}/history`);
    baselineHistoryCount = Array.isArray(history) ? history.length : 0;
  } catch (_err) {
    baselineHistoryCount = 0;
  }

  const poller = startRunAllLivePolling(base, baselineHistoryCount);

  try {
    const runAll = await postJson(`${base}/run-all`, { intent, agent_mode: mode });
    poller.stop();
    liveReasoning.textContent = 'Paso 2/4: run-all completado, evaluando decision...';

    const goNoGo = await getJson(`${base}/go-no-go`);
    liveReasoning.textContent = 'Paso 3/4: consultando bundle de auditoria...';

    const bundle = await getJson(`${base}/bundle`);
    liveReasoning.textContent = 'Paso 4/4: analisis listo para usuario.';

    decision.textContent = JSON.stringify(
      {
        final_signal: runAll.final_signal,
        decision: goNoGo.decision,
        reason_summary: goNoGo.reasons,
      },
      null,
      2
    );

    const action = goNoGo.decision === 'GO'
      ? 'Puedes continuar al siguiente objetivo del proyecto.'
      : goNoGo.decision === 'GO_CONDICIONAL'
        ? 'Continua con cautela y revisa las alertas de fases incompletas.'
        : 'Recomendado: reintentar con intent mas especifico o revisar bloqueo en fase temprana.';
    nextAction.textContent = action;
    renderDecisionBadge(goNoGo.decision, runAll.final_signal);
    plainExplanation.textContent = buildPlainExplanation(goNoGo, bundle);

    bundleSummary.textContent = JSON.stringify(
      {
        phase_results: (bundle.phase_results || []).length,
        telemetry: (bundle.telemetry || []).length,
        snapshots: (bundle.snapshots || []).length,
        ledger: (bundle.ledger || []).length,
      },
      null,
      2
    );
    const finalCount = Math.min((bundle.phase_results || []).length, 12);
    const finalPercent = Math.min(100, Math.round((finalCount / 12) * 100));
    progressBar.style.width = `${finalPercent}%`;
    progressText.textContent = `Progreso: ${finalCount}/12 fases`;
  } catch (err) {
    poller.stop();
    liveReasoning.textContent = `Error durante ejecucion: ${err.message}`;
    decisionBadge.className = 'decision-badge decision-no-go';
    decisionBadge.textContent = 'Error de ejecucion';
    plainExplanation.textContent = 'No fue posible completar el analisis. Verifica conexion, servidor y parametros antes de reintentar.';
  } finally {
    runAllButton.disabled = false;
  }
});
