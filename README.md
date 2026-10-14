# Powerball Quant Lab — v3.0

Aplicación local de investigación probabilística de **Powerball Australia**, construida con **Python, NumPy, SciPy y FastAPI**, y un dashboard web (HTML/CSS/JavaScript). No se necesita una cuenta ni una API de pago.

**Aviso:** con un sorteo justo, todas las combinaciones completas tienen la misma probabilidad de premio mayor: **1 entre 134.490.400**. Ningún modelo de esta aplicación ha demostrado obtener números más probables. El proyecto es para educación y experimentación científica, no una recomendación de apuesta.

## Instalación y ejecución

**Windows:** descomprime el ZIP y haz doble clic en `iniciar_windows.bat`. Requiere Python 3.10+ e internet la primera vez para instalar las librerías. Abre http://127.0.0.1:8000 o espera a que el iniciador lo abra.

**macOS / Linux:** desde la carpeta del proyecto:

```bash
python3 -m pip install -r requirements.txt
python3 run.py
```

**Docker** (opcional):

```bash
docker build -t powerball-quant-lab .
docker run --rm -p 8000:8000 powerball-quant-lab
```

La aplicación puede utilizarse sin internet después de instalar dependencias y mientras no se soliciten actualizaciones web. Los archivos de datos y el registro de pronósticos se guardan localmente.

## Qué hay en la v3

Las pestañas originales se mantienen: `Históricos`, `Backtesting` (17 modelos), `Pruebas estadísticas`, `Monte Carlo`, `Combinaciones` y `Datos`.

La nueva pestaña **Predictive Edge** incluye:

1. **Bayes empírico con pooling:** aproximación de shrinkage entre números, con estimación común de sobredispersión. No es una posterior física exacta ni un modelo jerárquico generativo completo.
2. **Regime guard:** heurística conservadora que necesita una diferencia grande entre una ventana reciente y otra anterior para apartarse del uniforme. Se analiza por separado la significancia de cambios mediante permutación de sorteos completos.
3. **Ensemble adaptativo:** combina los modelos simples originales y los anteriores. Siempre asigna **al menos 65%** de peso al uniforme; los restantes pesos usan solamente pérdidas anteriores a cada pronóstico. Ajusta ventana e intensidad de ponderación con el año de validación, sin consultar el año de test.
4. **Comparador v2 vs. v3:** Brier de 35 indicadores de aparición por sorteo y log-loss de Powerball, con mejora frente al uniforme, gráficos cronológicos e intervalos exploratorios simultáneos por bootstrap pareado por bloques.
5. **Pruebas placebo de sorteo justo:** crea historiales independientes, recalibra el ensemble con validación e informa cuán raro sería el **mejor** resultado de las tres alternativas avanzadas bajo lotería justa. Esta prueba **no incluye todos los modelos v2 ni otras ideas investigadas antes**.
6. **Distribución siguiente sorteo:** mapa de estimaciones del ensemble y, por separado, intervalos marginales creíbles al 90% derivados de Beta(20,80) y Beta(5,95) con prior fija K=100. No son intervalos de la estimación empírico-bayesiana, ni simultáneos, ni prueba de sesgo.
7. **Comparador de combinaciones:** genera una selección uniforme y una selección ponderada por el ensemble. El segundo procedimiento es una muestra heurística sin reemplazo: sus probabilidades de inclusión no necesariamente coinciden con las marginales introducidas. No implica mejor oportunidad de jackpot.
8. **Predicción sellada prospectiva:** registra los vectores completos de probabilidad, parámetros, fecha/hora UTC, sorteo objetivo y hash SHA-256 en `data/forecast_ledger.jsonl`, sin sobrescribir un registro existente para el mismo sorteo. Se bloquea el sellado desde el día del sorteo (UTC); cuando se incorpora el sorteo a la base, se evalúa el pronóstico original.
9. **Coocurrencias:** compara las 595 parejas de números y aplica un contraste Monte Carlo global del mayor desvío, corrigiendo por haber buscado entre todos los pares.
10. **Auditoría del CSV:** estadísticas de fechas, continuidad del ID, integridad automática, fuente secundaria y SHA-256 de la base incluida.

El ledger proporciona trazabilidad local, **no un sello criptográfico de tiempo de un tercero**: un administrador con acceso al disco podría modificar el archivo y recalcular su hash. Para validación fuerte, publique hashes de pronósticos a un servicio externo antes del sorteo.

## Datos históricos

El CSV empaquetado incluye **443 sorteos**, desde el #1144 (2018-04-19) hasta el #1586 (2026-10-08). Fuente secundaria: [archivo Powerball Australia de Powerball.net](https://www.powerball.net/australia/archive/2026). Se validan rangos, fechas, jueves, duplicados y continuidad de numeración. **No se han cotejado de forma independiente los 443 registros uno por uno con el operador oficial**. Ver `data/SOURCES.md` y la pestaña Datos.

Al importar registros nuevos: los conflictos se rechazan sin sobrescribir; la interfaz recalcula al recargar. Mientras un año nuevo tenga menos de diez sorteos, el último año de prueba completo elegible se mantiene para evitar que el dashboard falle en enero.

## Metodología de backtesting

- Para cada sorteo `t`, las probabilidades usan solamente los sorteos con índice anterior a `t`.
- El antepenúltimo año y los anteriores sirven como historial. El penúltimo año (`2025` en el conjunto actual) sirve para elegir parámetros del ensemble y el mejor modelo legado. El último (`2026`) se usa exclusivamente para prueba.
- Las pérdidas observadas del año de prueba pueden alimentar la **actualización online para pronósticos posteriores** del mismo año, pero nunca cambian los hiperparámetros seleccionados con validación.
- Los IC del test son exploratorios, obtenidos por bootstrap circular pareado de bloques de cuatro semanas. La muestra actual de 2026 contiene solo 41 sorteos: no permite concluir ventaja económica.
- El contraste de cambios de régimen permuta sorteos completos y corrige la búsqueda entre muchos cortes. Es una prueba de **estabilidad temporal**, no una prueba global de sorteo justo; esta última ya está en `Pruebas estadísticas`.
- Las pruebas placebo repiten **la selección del ensemble** y la selección de la mejor entre tres familias avanzadas en el holdout. No corrigen la búsqueda histórica de hipótesis previa.

## API local

| Método | Ruta | Propósito |
|---|---|---|
| GET | `/api/meta` | Datos de la aplicación |
| GET | `/api/edge` | Pronóstico y validación v3 (cacheada por archivo) |
| GET | `/api/edge-export` | Descarga informe completo JSON |
| GET | `/api/audit` | Auditoría del CSV |
| POST | `/api/regimes` | Permutaciones para cambios de régimen |
| POST | `/api/edge-null` | Simulaciones placebo del pipeline v3 |
| POST | `/api/pairs` | Contraste global de los 595 pares (requiere token remoto) |
| POST | `/api/edge-tickets` | Par de combinaciones uniformes y ponderadas |
| GET | `/api/ledger` | Ver predicciones registradas y evaluar resueltas |
| POST | `/api/ledger/lock` | Registrar pronóstico pre-sorteo |
| GET | `/api/download` | Descargar CSV |

Rutas que importan datos, actualizan históricos, sellan predicciones o ejecutan experimentos placebo/cambio de régimen exigen acceso **localhost** (si no hay token) o un `POWERBALL_ADMIN_TOKEN` definido en el servidor. El panel toma ese token en la pestaña Datos y lo envía en cabecera `X-Admin-Token` al ejecutar las acciones. No publiques el servidor sin autenticación, cuotas y revisión de seguridad adicionales.

## Estructura

```text
Powerball_Quant_Lab/
├── app/
│   ├── engine.py           # 17 modelos y pruebas originales
│   ├── advanced.py         # motor predictivo v3, tests placebo, ledger
│   ├── data.py             # CSV, validación, fuentes
│   ├── server.py           # API FastAPI
│   └── static/             # dashboard independiente de frameworks JS
├── data/
│   ├── powerball_australia.csv
│   ├── SOURCES.md
│   └── forecast_ledger.jsonl  # creado al sellar predicción, no incluido
├── reports/
│   ├── reporte_edge_v3.json
│   ├── regimenes_v3.json
│   ├── pares_v3_3000.json
│   └── placebos_v3_200.json
├── tests/
├── iniciar_windows.bat
├── RESULTADOS_V3.md
└── run.py
```

Para pruebas automatizadas:

```bash
python -m pip install pytest httpx
python -m pytest -q
```

La versión empacada superó **23 pruebas** en este entorno. La interfaz también se renderizó y se ejercitaron sus controles en Chromium sin errores JavaScript, usando respuestas reales de la API obtenidas con TestClient e inyectadas en la página debido a las restricciones de navegación local del entorno de validación. No se validó un despliegue público en producción.

## Publicación en Render

La configuración verificada para Render está en [`DEPLOY_RENDER.md`](DEPLOY_RENDER.md) y `render.yaml`. El plan gratuito es demostrativo, de solo lectura. Para persistencia, usa disco en un servicio de pago y `POWERBALL_STORAGE_DIR`.
