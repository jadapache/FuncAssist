# Pruebas de carga (Locust)

Requisitos: `pip install -r requirements-dev.txt` y un backend en ejecución con un
usuario **aprobado** dedicado a las pruebas (no uses el admin de producción).

```bash
cd backend
export LOAD_USERNAME=loadtest LOAD_PASSWORD='...'
# Interfaz web en http://localhost:8089
locust -f loadtests/locustfile.py --host https://localhost:8000

# Sin interfaz: 50 usuarios, 5/s de rampa, 5 minutos, con reportes
mkdir -p reports
locust -f loadtests/locustfile.py --host https://localhost:8000 \
  --headless -u 50 -r 5 -t 5m --csv reports/load --html reports/load.html
```

Variables:

| Variable | Defecto | Uso |
|---|---|---|
| `LOAD_USERNAME` / `LOAD_PASSWORD` | — | Credenciales del usuario de prueba |
| `LOAD_VERIFY_TLS` | `1` | `0` para certificados autofirmados en local |
| `LOAD_MAX_P95_MS` | `800` | p95 máximo aceptado (ms) |
| `LOAD_MAX_FAIL_RATIO` | `0.01` | Proporción máxima de errores |

Si se incumple un umbral, Locust termina con código 1. Filtra escenarios con
`--tags health` / `--exclude-tags knowledge`.

Perfiles sugeridos: **humo** (`-u 5 -t 1m`), **carga** esperada (`-u 50 -t 10m`),
**estrés** (subir `-u` hasta que el p95 o los errores rompan el SLO) y
**resistencia** (`-u 30 -t 1h`, vigilar memoria y pool de conexiones de PostgreSQL).

Los endpoints que llaman a LLM no se incluyen: miden al proveedor y generan coste.
