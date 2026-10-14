# Resultados — Powerball Quant Lab v2

**Fecha de ejecución:** 14 de octubre de 2026  
**Juego:** Powerball Australia (7 de 35 + 1 de 20)  
**Histórico:** **443 sorteos**, del 19-04-2018 al 08-10-2026 (consecutivos, {2018: 37, 2019: 52, 2020: 53, 2021: 52, 2022: 52, 2023: 52, 2024: 52, 2025: 52, 2026: 41})  
**Fuente:** powerball.net, fuente secundaria. Ver `data/SOURCES.md` para trazabilidad y limitaciones.

## Backtesting walk-forward

- Entrenamiento secuencial: solo sorteos anteriores al objetivo.
- Año de selección de modelos: **2025** (52 sorteos).
- Año de prueba posterior, sin usarlo para seleccionar modelos: **2026** (41 sorteos).
- Modelo seleccionado para números principales: **Ventana 13 · K=100**.
- Brier del seleccionado en 2026: **0.16029468**; Brier uniforme: **0.16000000**.
- Ganancia contra uniforme (Brier menor = mejor): **-0.00029468**.
- IC95% simultáneo contra 16 alternativas (bootstrap circular pareado, bloque de 4, 1.800 replicaciones): **[-0.00108714; +0.00049778]**.
- Modelo seleccionado para Powerball: **Uniforme · referencia**.
- Mejor Brier visto en 2026 (selección retrospectiva, no válida para recomendar ex ante): **Toda la historia · K=300**, Brier 0.15995265. Esta clasificación a posteriori no es predictiva.
- **Ninguna de las 16 alternativas** tiene intervalo simultáneo de ganancia completamente positivo en 2026, ni para números principales ni para Powerball.

## Pruebas Monte Carlo con 443 sorteos

Con 2.000 réplicas y semilla 42: prueba global de los principales p=0.7641; prueba del máximo entre 35 números p=0.6232; Powerball p=0.2404. Estos resultados no ofrecen una desviación estadísticamente concluyente de la extracción justa en las pruebas realizadas.

## Interpretación

El suavizado ayuda a evitar sobreajustar frecuencias, pero **ningún modelo demostró una ventaja predictiva robusta sobre el uniforme**. La probabilidad real del jackpot sigue siendo 1 entre 134.490.400 bajo las reglas actuales y extracción justa. Los IC del backtest son exploratorios (muestra 2026 corta), dependen del procedimiento bootstrap y **no son evidencia de que un número sea físicamente más probable**. Se recomienda seguimiento prospectivo y verificación oficial del archivo histórico.

El detalle por modelo, parámetros, métricas e IC se encuentra en `data/model_comparison_2026.json` y se visualiza en el dashboard, pestaña **Backtesting**.
