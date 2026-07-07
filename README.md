# Tarjetazo

Bot que detecta el resumen mensual de la tarjeta VISA BNA en tu casilla de Gmail,
lo desencripta, extrae y categoriza los gastos, y te manda un resumen lindo por Telegram
comparándolo contra el mes anterior.

## Cómo funciona

El resumen de BNA (`NAVI@mailing.bna.com.ar`) llega a una casilla de Outlook/Hotmail que,
mediante una regla, lo reenvía/redirige a una casilla de Gmail. Leemos Gmail por IMAP con
un app password (Outlook dejó de aceptar app passwords por IMAP desde sep-2024).

1. `email_client.py` busca por IMAP el último mail no leído que mencione a
   `NAVI@mailing.bna.com.ar` con un PDF adjunto. El mail se marca como leído **solo**
   cuando todo el pipeline terminó bien, para no perder el resumen del mes si algo falla.
2. `pdf_parser.py` desencripta el PDF (contraseña = tu DNI), extrae cada movimiento
   (fecha, comercio, monto en pesos y dólares), el período y el saldo total.
3. `categorize.py` clasifica cada comercio por reglas de palabras clave; lo que no matchea
   ninguna regla se manda a Claude (si `ANTHROPIC_API_KEY` está seteada) para nombrarlo y
   categorizarlo. Los comercios ya investigados se cachean en `data/comercios_conocidos.json`
   para no volver a consultarlos.
4. `formatter.py` arma un mensaje agrupado por categoría con subtotales, total, y la
   comparación contra el período anterior.
5. `historico.py` guarda cada período procesado en `data/historico.json` para poder comparar.
6. `telegram_bot.py` manda el mensaje a tu chat de Telegram.
7. `main.py` orquesta todo: valida que el total calculado cuadre con el saldo del resumen
   (avisa si no), guarda el estado, y si hace mucho que no procesa un resumen nuevo manda
   una alerta de "silencio" por si el bot se rompió.

## Setup local (para probar)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
# completar .env con tus credenciales reales
./run.sh
```

## Credenciales necesarias (completar en `.env`)

- **`EMAIL_USER`** / **`EMAIL_APP_PASSWORD`**: la dirección de Gmail y un app password de esa
  cuenta. Se genera en https://myaccount.google.com/apppasswords (requiere tener la
  verificación en 2 pasos activada).
- **`PDF_PASSWORD`**: la clave del PDF del resumen BNA (tu DNI).
- **`TELEGRAM_BOT_TOKEN`** y **`TELEGRAM_CHAT_ID`**: creá un bot con `@BotFather` en Telegram
  (`/newbot`), mandale un mensaje al bot, y después corré
  `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` para ver tu `chat_id` en la respuesta.
- **`ANTHROPIC_API_KEY`** (opcional): de https://console.anthropic.com — si no la ponés,
  los comercios no reconocidos por las reglas van a la categoría "Otros".

## Deploy en el VPS de Hetzner

```bash
# 1. Copiar el proyecto al servidor
rsync -avz --exclude venv --exclude data ./ usuario@tu-vps:/opt/tarjetazo/

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

El timer corre cada 6 horas (0, 6, 12, 18hs) y no hace nada si no hay un mail nuevo de BNA sin
leer o si ya fue procesado antes — así que es seguro dejarlo corriendo indefinidamente.

## Ajustar categorías

Las reglas de categorización están en `src/categorize.py`, en la lista `REGLAS`. Cada entrada es
`(regex, categoría)` y se evalúan en orden contra el texto del comercio en mayúsculas.
