# DuetMind (v0 bootstrap)

Implementacion inicial del sistema multiagente hibrido definido en el plan v1.5.

Incluye:
- FSM epistemica determinista con prioridades de colision.
- Arbitraje IA-M stateless (senal estructurada).
- Mensajeria JSON canonica compacta (Pydantic).
- Middleware de reparacion JSON por capas.
- Memoria dual en SQLite (snapshots + telemetria).
- Ledger criptografico basico de integridad de grafo.
- Score costo-eficiente con penalizacion financiera.

## Ejecutar demo

```powershell
cd d:\DuetMind
python -m pip install -e .
python -m duetmind.main --demo
```

## Servidor HTTP de auditoria

```powershell
python -m duetmind.main --serve-http --port 8000
```

Proteccion opcional por API key:

```powershell
python -m duetmind.main --serve-http --port 8000 --api-key secret-key
```

En ese modo, los endpoints protegidos requieren la cabecera `X-API-Key: secret-key`.

Endpoints disponibles:
- `GET /health`
- `GET /history`
- `GET /history?phase_id=1`
- `GET /telemetry`
- `GET /snapshots`
- `GET /bundle`
- `POST /run-phase`
- `POST /run-all`
- `POST /export-bundle`

## Exportacion de auditoria

```powershell
python -m duetmind.main --export-history history.json
python -m duetmind.main --export-bundle audit.json
python -m duetmind.main --telemetry-summary
```

## Preparar distribucion

```powershell
python -m duetmind.main --export-distribution-manifest distribution-manifest.json
python -m duetmind.main --prepare-distribution staging
```

Por defecto se genera un layout objetivo para Windows. Para Linux:

```powershell
python -m duetmind.main --prepare-distribution staging-linux --distribution-platform linux
```

Eso crea un staging autocontenido con `launcher-config.json`, `distribution-manifest.json` y la arbolizacion base para `resources/`, `engines/`, `models/` y `workspace/`.

## Empaquetar backend

```powershell
python -m duetmind.main --export-backend-spec backend_core.spec
python -m duetmind.main --prepare-backend-packaging backend-build
```

Eso genera un `backend_core.spec` listo para PyInstaller y un staging con `backend-packaging-manifest.json` y script de build para la plataforma seleccionada.

HTTP export bundle:

```powershell
curl -X POST http://127.0.0.1:8000/export-bundle -H "Content-Type: application/json" -d "{\"path\":\"audit.json\"}"
```

Custom run-all schedule:

```powershell
curl -X POST http://127.0.0.1:8000/run-all -H "Content-Type: application/json" -d "{\"intent\":\"demo\",\"schedule\":[{\"phase_id\":1,\"name\":\"CustomConcepcion\",\"environment\":\"local\",\"max_iterations\":1,\"model_tier\":\"custom\"}]}"
```

## Nota

Esta version es un bootstrap funcional para empezar implementacion. Los agentes IA-A/IA-B reales se inyectan despues via adaptadores de proveedores (cloud/local).