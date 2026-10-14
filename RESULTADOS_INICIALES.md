# Resultados iniciales — Powerball Quant Lab

**Fecha del análisis:** 9 de octubre de 2026  
**Juego:** Powerball Australia · 7 de 35, más Powerball de 1 a 20.  
**Histórico incluido:** 145 sorteos semanales, del 4 de enero de 2024 al 8 de octubre de 2026.

## Validación cronológica

La selección del modelo de los números principales se hizo **solo con sorteos de 2025 (52)**, evaluando cada pronóstico con datos anteriores. El ganador de ese período fue *Ventana 13 sorteos, K=100*.

En el año posterior, **2026 (41 sorteos)**, el modelo alcanzó un Brier medio de **0,16029468**, frente al **0,16000000** del modelo uniforme. Es decir, la mejora respecto de la referencia fue negativa, **−0,00029468**. El intervalo bootstrap pareado del 95 % para esa diferencia fue aproximadamente **[−0,00085332; 0,00026326]**; no demuestra una ventaja estadística.

Para predecir la Powerball separada, el mejor modelo seleccionado en 2025 fue el propio **uniforme**.

## Pruebas de uniformidad

Con **2.000 réplicas Monte Carlo** (semilla 42), para toda la base de 145 sorteos:

- Frecuencias principales, prueba global: **p ≈ 0,4703**.
- Máxima desviación de un número principal (considerando los 35): **p ≈ 0,8066**.
- Frecuencias de Powerball: **p ≈ 0,1964**.

Estas pruebas **no detectan una desviación estadística concluyente** respecto de la distribución uniforme. Eso no equivale a demostrar que el proceso físico es perfecto ni autoriza afirmaciones predictivas.

## Siguiente investigación

1. Abrir **Datos → Actualizar históricos** en la aplicación para intentar incorporar archivos anuales desde abril de 2018. El servidor requiere acceso externo y el sitio de origen puede cambiar el HTML; cualquier año que no se pueda verificar quedará marcado como error.
2. Si la descarga falla, importar CSV contrastados con el operador. El motor rechaza formatos anteriores al 19 de abril de 2018 y conflictos entre resultados.
3. Volver a calcular las pruebas y la validación, y definir un período prospectivo posterior que no haya servido para seleccionar modelos.

**Nota metodológica:** aunque una distribución estimada atribuya valores marginales ligeramente diferentes a ciertos números, eso no cambia la probabilidad de jackpot de **1/134.490.400** para ninguna combinación bajo el sorteo justo.

### Fuentes

- [Lotterywest, cambio de reglas del juego (abril 2018)](https://www.lotterywest.wa.gov.au/lotterywest/media-centre/powerball-to-deliver-more-winners-and-bigger-jackpots)
- [Powerball.net, archivo australiano](https://www.powerball.net/australia/archive/2026)
