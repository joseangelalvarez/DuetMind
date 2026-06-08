const baseUrlInput = document.getElementById('baseUrl');
const healthStatus = document.getElementById('healthStatus');
const intentInput = document.getElementById('intent');
const agentMode = document.getElementById('agentMode');
const liveReasoning = document.getElementById('liveReasoning');
const decision = document.getElementById('decision');
const nextAction = document.getElementById('nextAction');
const bundleSummary = document.getElementById('bundleSummary');

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

  liveReasoning.textContent = 'Paso 1/4: enviando solicitud run-all...';
  try {
    const runAll = await postJson(`${base}/run-all`, { intent, agent_mode: mode });
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
  } catch (err) {
    liveReasoning.textContent = `Error durante ejecucion: ${err.message}`;
  }
});
