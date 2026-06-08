const baseUrlInput = document.getElementById('baseUrl');
const healthStatus = document.getElementById('healthStatus');
const healthHeartbeat = document.getElementById('healthHeartbeat');
const intentInput = document.getElementById('intent');
const agentMode = document.getElementById('agentMode');
const liveReasoning = document.getElementById('liveReasoning');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const phaseFeed = document.getElementById('phaseFeed');
const phaseTimeline = document.getElementById('phaseTimeline');
const etaText = document.getElementById('etaText');
const decisionBadge = document.getElementById('decisionBadge');
const decision = document.getElementById('decision');
const nextAction = document.getElementById('nextAction');
const plainExplanation = document.getElementById('plainExplanation');
const bundleSummary = document.getElementById('bundleSummary');
const runAllButton = document.getElementById('btnRunAll');
const copyExecutiveButton = document.getElementById('btnCopyExecutive');
const downloadExecutiveTxtButton = document.getElementById('btnDownloadExecutiveTxt');
const downloadExecutiveJsonButton = document.getElementById('btnDownloadExecutiveJson');
const copyStatus = document.getElementById('copyStatus');
const runHistory = document.getElementById('runHistory');
const TOTAL_PHASES = 12;
const HISTORY_KEY = 'duetmind_run_history_v1';
const MAX_HISTORY = 5;
let latestExecutiveSummary = '';
let latestExecutivePayload = null;

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
    const signal = String(row.signal || '');
    if (signal === 'CONVERGE_CONDICIONADO') {
      item.classList.add('feed-ok');
    } else if (signal === 'ESCALAR_A_HUMANO' || signal === 'ABORTAR' || signal === 'REINICIAR_DESDE_PROMPT_3') {
      item.classList.add('feed-error');
    } else {
      item.classList.add('feed-warn');
    }
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

function buildExecutiveSummary(runAll, goNoGo, bundle) {
  const phases = (bundle.phase_results || []).length;
  const telemetry = (bundle.telemetry || []).length;
  const blockers = (goNoGo.blocking_signals || []).length;
  const reasons = Array.isArray(goNoGo.reasons) ? goNoGo.reasons.join(', ') : 'sin detalles';
  return [
    'Resumen Ejecutivo DuetMind',
    `- Senal final: ${runAll.final_signal}`,
    `- Decision: ${goNoGo.decision}`,
    `- Fases registradas: ${phases}/${TOTAL_PHASES}`,
    `- Eventos de telemetria: ${telemetry}`,
    `- Bloqueos detectados: ${blockers}`,
    `- Motivos principales: ${reasons}`,
  ].join('\n');
}

function safeLoadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (_err) {
    return [];
  }
}

function saveHistory(entries) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
}

function renderRunHistory() {
  const entries = safeLoadHistory();
  runHistory.innerHTML = '';
  if (entries.length === 0) {
    const item = document.createElement('li');
    item.textContent = 'Aun no hay corridas guardadas en este navegador.';
    runHistory.appendChild(item);
    return;
  }

  for (const entry of entries) {
    const item = document.createElement('li');
    const timestamp = new Date(entry.timestamp).toLocaleString('es-ES');
    item.textContent = `${timestamp} | ${entry.decision} | senal ${entry.finalSignal} | fases ${entry.phases}/${TOTAL_PHASES} | score medio ${entry.averageScore}`;
    runHistory.appendChild(item);
  }
}

function appendRunHistory(runAll, goNoGo, bundle) {
  const entries = safeLoadHistory();
  const next = {
    timestamp: Date.now(),
    decision: String(goNoGo.decision || 'UNKNOWN'),
    finalSignal: String(runAll.final_signal || ''),
    phases: Number((bundle.phase_results || []).length),
    averageScore: typeof goNoGo.average_score === 'number' ? goNoGo.average_score.toFixed(3) : 'n/a',
  };
  entries.unshift(next);
  saveHistory(entries.slice(0, MAX_HISTORY));
  renderRunHistory();
}

function downloadFile(fileName, content, contentType) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function formatSeconds(seconds) {
  const safeSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remSeconds = safeSeconds % 60;
  if (minutes === 0) {
    return `${remSeconds}s`;
  }
  return `${minutes}m ${remSeconds}s`;
}

function signalToTimelineState(signalValue) {
  if (signalValue === 'ESCALAR_A_HUMANO' || signalValue === 'ABORTAR' || signalValue === 'REINICIAR_DESDE_PROMPT_3') {
    return 'blocked';
  }
  return 'done';
}

function renderPhaseTimeline(rows, isRunning, startedAtMs) {
  const byPhase = new Map();
  for (const row of rows) {
    byPhase.set(Number(row.phase_id), row);
  }

  const completed = byPhase.size;
  const nextRunningPhase = Math.min(TOTAL_PHASES, completed + 1);

  phaseTimeline.innerHTML = '';
  for (let phase = 1; phase <= TOTAL_PHASES; phase += 1) {
    const row = byPhase.get(phase);
    let state = 'pending';
    let label = 'Pendiente';

    if (row) {
      state = signalToTimelineState(String(row.signal || ''));
      label = state === 'blocked' ? `Bloqueada: ${row.signal}` : `Completada: ${row.signal}`;
    } else if (isRunning && phase === nextRunningPhase) {
      state = 'running';
      label = 'En ejecucion';
    }

    const item = document.createElement('li');
    item.className = `phase-${state}`;
    item.textContent = `Fase ${phase} - ${label}`;
    phaseTimeline.appendChild(item);
  }

  if (!isRunning) {
    etaText.textContent = 'Duracion estimada restante: corrida finalizada';
    return;
  }

  if (completed === 0) {
    etaText.textContent = 'Duracion estimada restante: por calcular';
    return;
  }

  const elapsedSeconds = (Date.now() - startedAtMs) / 1000;
  const avgPerPhase = elapsedSeconds / completed;
  const remaining = Math.max(0, TOTAL_PHASES - completed);
  const etaSeconds = remaining * avgPerPhase;
  etaText.textContent = `Duracion estimada restante: ${formatSeconds(etaSeconds)} (promedio ${formatSeconds(avgPerPhase)} por fase)`;
}

function startRunAllLivePolling(base, baselineHistoryCount) {
  const state = { active: true };
  const startedAtMs = Date.now();

  const poll = async () => {
    if (!state.active) {
      return;
    }
    try {
      const history = await getJson(`${base}/history`);
      const rows = Array.isArray(history) ? history : [];
      const newRows = rows.slice(baselineHistoryCount);
      const completed = newRows.length;
      const percent = Math.min(100, Math.round((completed / TOTAL_PHASES) * 100));

      progressBar.style.width = `${percent}%`;
      progressText.textContent = `Progreso: ${Math.min(completed, TOTAL_PHASES)}/${TOTAL_PHASES} fases`;
      renderPhaseFeed(newRows);
      renderPhaseTimeline(newRows, true, startedAtMs);

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
    startedAtMs,
  };
}

document.getElementById('btnHealth').addEventListener('click', async () => {
  const base = baseUrlInput.value.trim();
  healthStatus.textContent = 'Comprobando servidor...';
  try {
    const health = await getJson(`${base}/health`);
    healthStatus.textContent = health.status === 'ok' ? 'Servidor conectado y listo.' : 'Servidor responde pero no esta listo.';
    healthHeartbeat.textContent = 'Auto-verificacion cada 8s activa.';
  } catch (err) {
    healthStatus.textContent = `No se pudo conectar: ${err.message}`;
    healthHeartbeat.textContent = 'Auto-verificacion activa, ultimo estado: sin conexion.';
  }
});

async function runPassiveHealthCheck() {
  const base = baseUrlInput.value.trim();
  try {
    const health = await getJson(`${base}/health`);
    if (health.status === 'ok') {
      healthHeartbeat.textContent = 'Auto-verificacion: servidor disponible.';
    } else {
      healthHeartbeat.textContent = 'Auto-verificacion: respuesta atipica del servidor.';
    }
  } catch (err) {
    healthHeartbeat.textContent = `Auto-verificacion: sin conexion (${err.message}).`;
  }
}

setInterval(runPassiveHealthCheck, 8000);
renderRunHistory();

document.getElementById('btnRunAll').addEventListener('click', async () => {
  const base = baseUrlInput.value.trim();
  const intent = intentInput.value.trim();
  const mode = agentMode.value;

  runAllButton.disabled = true;
  progressBar.style.width = '0%';
  progressText.textContent = `Progreso: 0/${TOTAL_PHASES} fases`;
  phaseFeed.innerHTML = '';
  renderPhaseTimeline([], true, Date.now());
  etaText.textContent = 'Duracion estimada restante: por calcular';
  decisionBadge.className = 'decision-badge decision-unknown';
  decisionBadge.textContent = 'En ejecucion';
  latestExecutiveSummary = '';
  latestExecutivePayload = null;
  copyStatus.textContent = 'El resumen ejecutivo estara disponible al finalizar la corrida.';
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
    const finalPercent = Math.min(100, Math.round((finalCount / TOTAL_PHASES) * 100));
    progressBar.style.width = `${finalPercent}%`;
    progressText.textContent = `Progreso: ${finalCount}/${TOTAL_PHASES} fases`;
    renderPhaseTimeline(bundle.phase_results || [], false, poller.startedAtMs);
    latestExecutiveSummary = buildExecutiveSummary(runAll, goNoGo, bundle);
    latestExecutivePayload = {
      generated_at: new Date().toISOString(),
      final_signal: runAll.final_signal,
      decision: goNoGo.decision,
      reasons: goNoGo.reasons,
      average_score: goNoGo.average_score,
      minimum_score: goNoGo.minimum_score,
      coverage: goNoGo.coverage,
      phase_results_count: (bundle.phase_results || []).length,
      telemetry_count: (bundle.telemetry || []).length,
      snapshots_count: (bundle.snapshots || []).length,
      ledger_count: (bundle.ledger || []).length,
    };
    appendRunHistory(runAll, goNoGo, bundle);
    copyStatus.textContent = 'Resumen ejecutivo listo para copiar.';
  } catch (err) {
    poller.stop();
    liveReasoning.textContent = `Error durante ejecucion: ${err.message}`;
    decisionBadge.className = 'decision-badge decision-no-go';
    decisionBadge.textContent = 'Error de ejecucion';
    plainExplanation.textContent = 'No fue posible completar el analisis. Verifica conexion, servidor y parametros antes de reintentar.';
    copyStatus.textContent = 'No hay resumen ejecutivo por error en la corrida.';
    renderPhaseTimeline([], false, poller.startedAtMs);
  } finally {
    runAllButton.disabled = false;
  }
});

copyExecutiveButton.addEventListener('click', async () => {
  if (!latestExecutiveSummary) {
    copyStatus.textContent = 'Aun no hay datos para copiar. Ejecuta run-all primero.';
    return;
  }

  try {
    await navigator.clipboard.writeText(latestExecutiveSummary);
    copyStatus.textContent = 'Resumen ejecutivo copiado al portapapeles.';
  } catch (_err) {
    copyStatus.textContent = 'No se pudo copiar automaticamente. Intenta desde un navegador con permisos de portapapeles.';
  }
});

downloadExecutiveTxtButton.addEventListener('click', () => {
  if (!latestExecutiveSummary) {
    copyStatus.textContent = 'No hay resumen TXT para descargar. Ejecuta run-all primero.';
    return;
  }
  downloadFile('duetmind-resumen-ejecutivo.txt', latestExecutiveSummary, 'text/plain;charset=utf-8');
  copyStatus.textContent = 'Resumen TXT descargado.';
});

downloadExecutiveJsonButton.addEventListener('click', () => {
  if (!latestExecutivePayload) {
    copyStatus.textContent = 'No hay resumen JSON para descargar. Ejecuta run-all primero.';
    return;
  }
  const content = JSON.stringify(latestExecutivePayload, null, 2);
  downloadFile('duetmind-resumen-ejecutivo.json', content, 'application/json;charset=utf-8');
  copyStatus.textContent = 'Resumen JSON descargado.';
});
