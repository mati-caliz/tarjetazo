# Tarjetazo

Bot que revisa tu casilla de Hotmail, detecta el resumen mensual de la tarjeta VISA BNA,
lo desencripta, extrae y categoriza los gastos, y te manda un resumen lindo por Telegram.

## Cómo funciona

1. `email_client.py` busca por IMAP el último mail no leído de `NAVI@mailing.bna.com.ar` con un PDF adjunto.
2. `pdf_parser.py` desencripta el PDF (contraseña = tu DNI) y extrae cada movimiento (fecha, comercio, monto).
3. `categorize.py` clasifica cada comercio por reglas de palabras clave; lo que no matchea ninguna regla
   se manda a la API de Claude (si `ANTHROPIC_API_KEY` está seteada) para clasificar automáticamente.
4. `formatter.py` arma un mensaje agrupado por categoría con subtotales y total.
5. `telegram_bot.py` lo manda a tu chat de Telegram.
6. `main.py` orquesta todo y guarda en `data/ultimo_procesado.txt` el ID del mail ya procesado,
   para no mandar el mismo resumen dos veces.

## Setup local (para probar)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
# completar .env con tus credenciales reales
./run.sh
```

## Credenciales necesarias (completar en `.env`)

- **`EMAIL_APP_PASSWORD`**: contraseña de aplicación de tu cuenta Outlook/Hotmail.
  Se genera en https://account.live.com/proofs/AppPassword (requiere tener verificación en 2 pasos activada).
- **`TELEGRAM_BOT_TOKEN`** y **`TELEGRAM_CHAT_ID`**: creá un bot con `@BotFather` en Telegram (`/newbot`),
  mandale un mensaje al bot, y después corré:
  `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` para ver tu `chat_id` en la respuesta.
- **`ANTHROPIC_API_KEY`** (opcional): de https://console.anthropic.com — si no la ponés,
  los comercios no reconocidos por las reglas van a la categoría "Otros".

## Deploy en el VPS de Hetzner

```bash
# 1. Copiar el proyecto al servidor
rsync -avz --exclude venv --exclude data/ultimo_procesado.txt ./ usuario@tu-vps:/opt/tarjetazo/

# 2. En el servidor: crear usuario de servicio, venv e instalar deps
ssh usuario@tu-vps
sudo useradd -r -s /bin/false tarjetazo || true
sudo chown -R tarjetazo:tarjetazo /opt/tarjetazo
cd /opt/tarjetazo
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env   # y completar con las credenciales reales
chmod 600 .env

# 3. Instalar el systemd timer
sudo cp deploy/tarjetazo.service /etc/systemd/system/
sudo cp deploy/tarjetazo.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tarjetazo.timer

# 4. Probar manualmente una corrida
sudo systemctl start tarjetazo.service
sudo journalctl -u tarjetazo.service -f
```

El timer corre cada 6 horas (0, 6, 12, 18hs) y no hace nada si no hay un mail nuevo de BNA sin leer
o si ya fue procesado antes — así que es seguro dejarlo corriendo indefinidamente.

## Ajustar categorías

Las reglas de categorización están en `src/categorize.py`, en la lista `REGLAS`. Cada entrada es
`(regex, categoría)` y se evalúan en orden contra el texto del comercio en mayúsculas.
