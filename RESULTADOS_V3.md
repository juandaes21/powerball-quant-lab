# Resultados reproducibles — Powerball Quant Lab v3

**Corte de datos:** 8 de octubre de 2026 (sorteo 1586). **Base:** 443 sorteos, desde 19-04-2018. **Selección:** 52 sorteos de 2025. **Prueba posterior:** 41 sorteos de 2026. Fuente histórica secundaria, no cotejada uno por uno con el operador.

## Comparación 2026

| Método | Brier principales ↓ | Mejora Brier vs uniforme ↑ | Log-loss Powerball ↓ | Mejora log-loss ↑ |
|---|---:|---:|---:|---:|
| Uniforme | 0,160000 | 0 | 2,995732 | 0 |
| Seleccionado v2 usando 2025 | 0,160295 | −0,000295 | 2,995732 | 0 |
| Bayes empírico (pooling) | 0,160000 | 0 | 2,996435 | −0,000703 |
| Régimen conservador | 0,160000 | 0 | 2,995732 | 0 |
| Ensemble adaptativo | 0,160013 | −0,000013 | 2,993112 | +0,002621 |

Brier: menor es mejor. En la comparación de Powerball, `log-loss` es la pérdida del valor correcto. Estos cambios son **muy pequeños**, y la aparente mejora de Powerball no es concluyente.

### Intervalos de confianza simultáneos (95%) del ensemble

- Ganancia de Brier: **[−0,000136; +0,000110]**.
- Ganancia de log-loss Powerball: **[−0,007367; +0,012608]**.

Ambos incluyen cero. Bootstrap pareado circular de bloques de cuatro sorteos, 2.200 réplicas. Intervalos exploratorios y condicionados a la configuración evaluada.

### Monte Carlo del modelo nulo justo: 200 historiales completos

Se volvió a seleccionar el ensemble usando la validación de cada historial y se buscó la mejor mejora de **tres familias avanzadas** en el holdout.

- Números principales: p de placebo **0,8507**.
- Powerball: p de placebo **0,2488**.

No hay evidencia convincente de ventaja predictiva. Los p no corrigen las 17 alternativas originales, ni hipótesis probadas previamente, ni el riesgo de cambios futuros.

### Estabilidad temporal: 1.500 permutaciones

Se evaluó el máximo estadístico sobre todos los puntos de corte elegibles, permutando sorteos completos y aplicando ajuste Bonferroni para principal y Powerball.

- Principales: mejor corte exploratorio a partir del 04-11-2021. **p ajustado = 1,000**.
- Powerball: mejor corte exploratorio a partir del 18-08-2022. **p ajustado = 1,000**.

No hay una ruptura temporal estadísticamente concluyente. Las fechas mencionadas son solo cortes que maximizan una estadística sobre esta muestra, no evidencia de cambios en máquinas físicas.

### Coocurrencias de 595 pares: 3.000 réplicas del sorteo justo

El par 09 + 22 apareció 30 veces frente a aproximadamente 15,64 esperadas. Sin embargo, se eligió *después* de buscar el más anómalo entre 595 pares: el test global del máximo desvío da un valor p en `reports/pares_v3_3000.json`, que **no indica una desviación concluyente**. La identificación de pares por frecuencia pasada no implica mayor probabilidad futura.

### Parámetros del ensemble seleccionados con 2025

- Números principales: ventana 104, intensidad η=400; 65% de peso mínimo al uniforme.
- Powerball: ventana 26, intensidad η=2; 65% de peso mínimo al uniforme.

La estimación siguiente es para el **sorteo 1587, el 15 de octubre de 2026**, si no se actualiza antes la base.

## Archivos para auditoría

- `reports/reporte_edge_v3.json`: errores, intervalos, todos los 35+20 marginales, calibración, trayectoria y pesos.
- `reports/regimenes_v3.json`: test de permutaciones y punto de corte.
- `reports/placebos_v3_200.json`: resultados por simulación placebo.
- `reports/pares_v3_3000.json`: pares extremos y p global corregido.
- `data/SOURCES.md`: origen del histórico y suma SHA-256 de los datos.

**Conclusión:** el modelo uniforme es actualmente el punto de referencia de mayor confianza. Nuestro laboratorio no ha demostrado números, Powerballs o combinaciones con probabilidad superior. La evolución correcta es sellar predicciones antes de cada sorteo y acumular evidencia sin modificar los resultados pasados.
