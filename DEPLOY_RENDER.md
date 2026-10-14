# Publicar Powerball Quant Lab v3 en Render

## Demo pública gratuita (sin persistencia)

1. Crea un repositorio **nuevo**, por ejemplo `powerball-quant-lab`, en GitHub.
2. Sube el contenido de esta carpeta al **directorio raíz** del repositorio, incluyendo `render.yaml`, `requirements.txt`, `app/` y `data/`.
3. En Render elige **New > Blueprint**, conecta el repositorio y aprueba la configuración de `render.yaml`. Alternativamente elige **New > Web Service** con runtime Python, comando de compilación `pip install -r requirements.txt`, inicio `uvicorn app.server:app --host 0.0.0.0 --port $PORT`, y ruta de salud `/api/health`.
4. Render asignará un dominio HTTPS `https://<servicio>.onrender.com`. Comprueba `/api/health` y `/api/meta`.

La plantilla gratuita incluye `POWERBALL_READ_ONLY=1` para **desactivar** las funciones que escriben históricos, ejecutan tareas caras protegidas o sellan pronósticos. Los gráficos, modelos y simulaciones se pueden consultar desde la web. Render Free puede entrar en reposo y los cambios al sistema de archivos se pierden en reinicios.

## Seguimiento prospectivo persistente (opción de pago)

Para conservar la base importada y los pronósticos sellados, configura un Web Service **de pago** con disco persistente (desde Render Dashboard):

- Monta el disco en `/var/data` (o directorio de tu elección).
- Establece `POWERBALL_STORAGE_DIR=/var/data`. En el primer inicio copiará el CSV inicial al disco; las actualizaciones posteriores no se sobrescriben durante reinicios.
- Establece `POWERBALL_READ_ONLY=0`.
- Establece `POWERBALL_ADMIN_TOKEN` a un secreto largo y único usando el panel Environment de Render. No lo guardes en GitHub; el dashboard pide este token para acciones privilegiadas.
- Conserva **una sola instancia de Uvicorn** para evitar carreras de escritura al CSV y al ledger JSONL.
- Haz copias de seguridad independientes del CSV y de `forecast_ledger.jsonl`. El ledger no es un sello de tiempo de terceros.

Si necesitas mayor concurrencia, gestión multiusuario o auditoría fuerte, migra el ledger a Postgres con transacciones y control de accesos antes de abrir las operaciones de escritura a múltiples usuarios.

## Límites y seguridad

- Ningún modelo ha demostrado pronosticar números más probables que un sorteo justo.
- En Render se limitan las peticiones de simulación a 100.000 sorteos y los tests públicos a 2.000 réplicas por solicitud.
- No publiques el token administrador y no habilites escritura pública sin control de usuarios, límites por IP y almacenamiento duradero.
- La base inicial tiene 443 sorteos hasta el 8 de octubre de 2026; no se actualiza sola.
- Si Render falla al iniciar, revisa **Logs** en el panel del servicio.
