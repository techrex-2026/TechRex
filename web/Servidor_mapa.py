"""
Servidor - RexScan · Sistema de Analisis y Preservacion de Fosiles
------------------------------------------------------------------
Portal con tres accesos:
  - Vista Publica (Museo) - abierta, galeria de especimenes + asistente
  - Acceso Campo          - login basico, monitoreo en vivo
  - Acceso Laboratorio    - login basico, analisis avanzado

INSTALACION (una sola vez):
    pip install flask pyserial

USO:
    1. Cambia PUERTO por tu puerto COM (ej: 'COM3')
    2. Ejecuta: python servidor.py
    3. En la PC:       
    4. En el celular:  http://[IP-de-tu-PC]:5000
"""

from flask import Flask, jsonify, render_template_string, send_file, request, redirect, url_for, session
import serial
import threading
import time
from datetime import datetime
import socket
import os

# CONFIGURACION
PUERTO  = 'COM6'   # <-- Cambia por tu puerto COM
BAUDIOS = 9600
ARCHIVO_CSV = f"fosil_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
MAX_HISTORIAL = 50

# Contrasenas de acceso (cambialas por las que quieras)
CLAVE_CAMPO       = "123"
CLAVE_LABORATORIO = "123"

# UMBRALES DE RIESGO POR TIPO DE ESPECIMEN
# Cada tipo de hueso tolera distinta humedad segun que tan protegido/expuesto esta.
# Edita nombre y umbral aqui cuando cambies los tipos entrenados en HuskyLens.
UMBRALES_HUMEDAD = {
    1: {"nombre": "Vertebra Caudal - LIMPIA",      "umbral": 40},
    2: {"nombre": "Vertebra Caudal - SUCIA",       "umbral": 55},
    3: {"nombre": "Vertebra Cervical Superior",    "umbral": 35},
    4: {"nombre": "Vertebra Cervical Inferior",    "umbral": 50},
}
UMBRAL_GENERICO = 45  # se usa si no hay hueso identificado (ID 0 o desconocido)

# CARPETA DE ESCANEOS 3D
# Cada escaneo guardado va aqui como archivo de texto, con el nombre del
# especimen al que pertenece:  ES-001.txt, ES-002.txt, etc.
# Son los archivos que genera el boton DESCARGAR PUNTOS del modulo de escaneo.
CARPETA_ESCANEOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'escaneos')

# El modulo de escaneo 3D corre como servidor aparte (servidor_escaner.py)
# en el puerto 5001. Se mantiene separado a proposito: si el escaner falla,
# el monitoreo -que es el nucleo del sistema- sigue funcionando.
PUERTO_ESCANER = 5001

# Debe coincidir con INTERVALO_LECTURA del Arduino (en segundos) para que
# la prediccion de tiempo hasta el umbral sea correcta.
INTERVALO_LECTURA_SEG = 5

# Cuantas lecturas recientes del MISMO especimen se usan para calcular tendencia
VENTANA_TENDENCIA = 10

# Coordenadas del sitio de excavacion (simuladas por ahora)
# Cambia estos numeros por los del lugar que quieras mostrar en el mapa.
# Ejemplo actual: Panama Viejo, Ciudad de Panama.
SITIO_LAT = 8.9959
SITIO_LNG = -79.4855
SITIO_NOMBRE = "Sitio de excavacion - Panama Viejo"

# GALERIA PUBLICA DE ESPECIMENES (edita libremente)
ESPECIMENES = {
    "ES-001": {
        "nombre": "Vértebra Cervical Superior",
        "emoji": "\U0001F9B4",
        "imagen": "/static/cervical_superior.jpeg",  
        "periodo": "Cretácico Inferior",
        "edad": "~124 millones de años",
        "tipo": "Vértebra del cuello (región superior)",
        "estado": "Optimo",
        "lugar": "Sitio de excavación, Panamá",
        "descripcion": "Vértebra de la parte alta del cuello del Hypsilophodon foxii, cercana a la cabeza. Al ser un dinosaurio pequeño y ágil, estas vértebras eran livianas y le permitían mover la cabeza con rapidez mientras se alimentaba o vigilaba a sus depredadores.",
        "preguntas": {
            "¿De qué animal es?": "Del Hypsilophodon foxii, un dinosaurio herbívoro pequeño y veloz que vivió en lo que hoy es Europa. Medía apenas 1,8 metros y pesaba unos 20 kilos.",
            "¿Cuántos años tiene?": "Alrededor de 124 millones de años, del período Cretácico Inferior.",
            "¿Por qué es importante?": "Las vértebras del cuello ayudan a entender cómo movía la cabeza este dinosaurio, clave para un animal que dependía de su agilidad para sobrevivir.",
            "¿Cómo se preservó?": "Su buen estado indica un enterramiento rápido que lo protegió de la humedad y el aire durante millones de años."
        }
    },
    "ES-002": {
        "nombre": "Vértebra Cervical Inferior",
        "emoji": "\U0001F9B4",
        "imagen": "/static/cervical_inferior.jpeg",  
        "periodo": "Cretácico Inferior",
        "edad": "~124 millones de años",
        "tipo": "Vértebra del cuello (región inferior)",
        "estado": "Medio",
        "lugar": "Sitio de excavación, Panamá",
        "descripcion": "Vértebra de la parte baja del cuello, donde este se une con el tronco. Es algo más robusta que las superiores, ya que soportaba la unión entre la cabeza, el cuello y el cuerpo del Hypsilophodon.",
        "preguntas": {
            "¿De qué animal es?": "Del mismo Hypsilophodon foxii; esta pieza corresponde a la base del cuello, cerca de los hombros.",
            "¿Cuántos años tiene?": "Cerca de 124 millones de años, del período Cretácico Inferior.",
            "¿Por qué es importante?": "Comparar las vértebras superiores e inferiores del cuello permite reconstruir su postura completa y cómo equilibraba la cabeza al correr.",
            "¿Cómo se preservó?": "Presenta porosidad leve por la humedad del suelo, por eso su estado es medio; aun así conserva bien su forma."
        }
    },
    "ES-003": {
        "nombre": "Vértebra Caudal",
        "emoji": "\U0001F9B4",
        "imagen": "/static/caudal.jpeg",  # <-- ej: "/static/caudal.jpg"
        "periodo": "Cretácico Inferior",
        "edad": "~124 millones de años",
        "tipo": "Vértebra de la cola",
        "estado": "Optimo",
        "lugar": "Sitio de excavación, Panamá",
        "descripcion": "Vértebra proveniente de la cola del Hypsilophodon. Su larga cola rígida actuaba como contrapeso al correr, dándole el equilibrio y la estabilidad que lo hacían uno de los dinosaurios más veloces de su época.",
        "preguntas": {
            "¿De qué animal es?": "Del Hypsilophodon foxii; esta pieza pertenece a la cola, fundamental para su equilibrio y velocidad.",
            "¿Cuántos años tiene?": "Aproximadamente 124 millones de años, del período Cretácico Inferior.",
            "¿Por qué es importante?": "La cola revela cómo mantenía el equilibrio al correr; era su gran ventaja para escapar de los depredadores.",
            "¿Cómo se preservó?": "Al ser una pieza compacta y densa, resistió bien el paso del tiempo, conservándose en estado óptimo."
        }
    },
    "ES-004": {
        "nombre": "Vértebra Caudal (sin limpiar)",
        "emoji": "\U0001F9B4",
        "imagen": "/static/caudal_sucia.jpeg",  # <-- ej: "/static/caudal_sucia.jpg"
        "periodo": "Cretácico Inferior",
        "edad": "~124 millones de años",
        "tipo": "Vértebra de la cola",
        "estado": "Poroso",
        "lugar": "Sitio de excavación, Panamá",
        "descripcion": "Vértebra de la cola recién extraída, aún cubierta de sedimento y sin limpiar. Su superficie porosa muestra el desgaste causado por la humedad del suelo, y requiere un proceso de limpieza cuidadoso antes de poder analizarse en detalle.",
        "preguntas": {
            "¿De qué animal es?": "Del Hypsilophodon foxii, al igual que las otras piezas; es otra vértebra de su larga cola.",
            "¿Cuántos años tiene?": "Aproximadamente 124 millones de años, del período Cretácico Inferior.",
            "¿Por qué está sucia?": "Fue recién extraída de la excavación y todavía conserva sedimento adherido. Antes de estudiarla hay que limpiarla con cuidado para no dañar el hueso.",
            "¿Por qué es importante limpiarla?": "El sedimento y la humedad aceleran la degradación del hueso. Limpiarla y registrar sus datos a tiempo es clave para preservar la información, y es justo lo que hace RexScan."
        }
    }
}

# Estado compartido (sistema en vivo)
ultimo_dato = {
    "lectura": 0, "fecha": "--/--/----", "hora": "--:--:--", "humedad": 0,
    "raw": 0, "hueso_presente": "NO", "id_huskylens": 0,
    "estado_suciedad": "SIN HUESO", "conectado": False, "ultima_actualizacion": None
}
historial = []
# Ubicacion del hallazgo (la marca campo, la ve laboratorio)
ubicacion_actual = {"lat": SITIO_LAT, "lng": SITIO_LNG, "nombre": SITIO_NOMBRE}
app = Flask(__name__)
app.secret_key = "rexscan-techrex-2026"


def leer_arduino():
    global ultimo_dato, historial
    while True:
        try:
            ser = serial.Serial(PUERTO, BAUDIOS, timeout=2)
            print(f"Conectado a {PUERTO}")
            ultimo_dato["conectado"] = True
            with open(ARCHIVO_CSV, 'w', newline='', encoding='utf-8') as f:
                f.write("Lectura,Fecha,Hora,Humedad_%,Valor_raw,Hueso_presente,ID_HuskyLens,Estado_suciedad\n")
            while True:
                linea = ser.readline().decode('utf-8', errors='ignore').strip()
                if not linea or "Lectura" in linea:
                    continue
                partes = linea.split(",")
                if len(partes) != 8:
                    continue
                try:
                    ultimo_dato = {
                        "lectura": int(partes[0]), "fecha": partes[1], "hora": partes[2],
                        "humedad": int(partes[3]), "raw": int(partes[4]),
                        "hueso_presente": partes[5], "id_huskylens": int(partes[6]),
                        "estado_suciedad": partes[7], "conectado": True,
                        "ultima_actualizacion": datetime.now().strftime("%H:%M:%S")
                    }
                    with open(ARCHIVO_CSV, 'a', newline='', encoding='utf-8') as f:
                        f.write(linea + "\n")
                    historial.append({
                        "lectura": ultimo_dato["lectura"], "humedad": ultimo_dato["humedad"],
                        "hora": ultimo_dato["hora"], "id_huskylens": ultimo_dato["id_huskylens"]
                    })
                    if len(historial) > MAX_HISTORIAL:
                        historial.pop(0)
                except (ValueError, IndexError):
                    continue
        except serial.SerialException:
            print(f"No se pudo conectar a {PUERTO}, reintentando en 3s...")
            ultimo_dato["conectado"] = False
            time.sleep(3)


def calcular_riesgo():
    """
    Calcula el nivel de riesgo actual del especimen detectado.
    No solo mira la humedad actual: calcula la tendencia (regresion lineal
    simple) de las ultimas lecturas del MISMO especimen y estima en cuantos
    minutos llegaria al umbral critico si la tendencia se mantiene.
    """
    id_actual = ultimo_dato.get("id_huskylens", 0)
    humedad_actual = ultimo_dato.get("humedad", 0)
    info = UMBRALES_HUMEDAD.get(id_actual)
    umbral = info["umbral"] if info else UMBRAL_GENERICO
    nombre_esp = info["nombre"] if info else "Sin especimen identificado"

    # Solo lecturas recientes del mismo especimen (evita mezclar tendencias
    # cuando cambia el hueso frente a la camara)
    puntos = [h for h in historial if h.get("id_huskylens") == id_actual][-VENTANA_TENDENCIA:]

    pendiente = 0.0
    minutos_estimados = None
    if len(puntos) >= 3:
        n = len(puntos)
        xs = list(range(n))
        ys = [p["humedad"] for p in puntos]
        prom_x = sum(xs) / n
        prom_y = sum(ys) / n
        num = sum((xs[i] - prom_x) * (ys[i] - prom_y) for i in range(n))
        den = sum((xs[i] - prom_x) ** 2 for i in range(n))
        pendiente = (num / den) if den != 0 else 0.0
        if pendiente > 0.01 and humedad_actual < umbral:
            lecturas_faltantes = (umbral - humedad_actual) / pendiente
            segundos = lecturas_faltantes * INTERVALO_LECTURA_SEG
            minutos_estimados = round(segundos / 60, 1)

    if humedad_actual >= umbral:
        nivel = "CRITICO"
    elif minutos_estimados is not None and minutos_estimados <= 5:
        nivel = "ALERTA"
    elif minutos_estimados is not None and minutos_estimados <= 15:
        nivel = "PRECAUCION"
    else:
        nivel = "NORMAL"

    return {
        "nivel": nivel,
        "especimen": nombre_esp,
        "umbral": umbral,
        "humedad_actual": humedad_actual,
        "tendencia_por_lectura": round(pendiente, 3),
        "minutos_estimados": minutos_estimados
    }


def leer_escaneo(id_esp):
    """
    Lee el archivo de puntos de un especimen y devuelve la lista de puntos.
    Cada punto es [x, y, z, fila, columna], igual que los genera el escaner.
    Devuelve lista vacia si no hay archivo o si esta mal formado.
    """
    ruta = os.path.join(CARPETA_ESCANEOS, f"{id_esp}.txt")
    if not os.path.isfile(ruta):
        return []

    puntos = []
    try:
        with open(ruta, 'r', encoding='utf-8', errors='ignore') as f:
            for linea in f:
                linea = linea.strip()
                if not linea.lower().startswith('p,'):
                    continue
                partes = linea.split(',')
                if len(partes) < 6:
                    continue
                try:
                    puntos.append([
                        float(partes[1]), float(partes[2]), float(partes[3]),
                        int(partes[4]), int(partes[5])
                    ])
                except ValueError:
                    continue   # linea cortada o incompleta: se ignora
    except OSError:
        return []

    return puntos


def escaneos_disponibles():
    """Ids de especimenes que tienen un escaneo guardado."""
    if not os.path.isdir(CARPETA_ESCANEOS):
        return []
    return [i for i in ESPECIMENES
            if os.path.isfile(os.path.join(CARPETA_ESCANEOS, f"{i}.txt"))]


def obtener_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


# RUTAS
@app.route('/')
def portal():
    # Se usa el host de la peticion para que el enlace funcione tanto en
    # esta PC como desde otro equipo de la red local.
    host = request.host.split(':')[0]
    return render_template_string(PAGINA_PORTAL,
                                  url_escaner=f"http://{host}:{PUERTO_ESCANER}/")

@app.route('/publico')
def publico():
    return render_template_string(PAGINA_PUBLICA, especimenes=ESPECIMENES)

@app.route('/especimen/<id_esp>')
def especimen(id_esp):
    esp = ESPECIMENES.get(id_esp)
    if not esp:
        return redirect(url_for('publico'))
    return render_template_string(PAGINA_DETALLE, esp=esp, id_esp=id_esp)

@app.route('/login/<destino>', methods=['GET', 'POST'])
def login(destino):
    error = ""
    if request.method == 'POST':
        clave = request.form.get('clave', '')
        if destino == 'campo' and clave == CLAVE_CAMPO:
            session['acceso_campo'] = True
            return redirect(url_for('campo'))
        elif destino == 'laboratorio' and clave == CLAVE_LABORATORIO:
            session['acceso_lab'] = True
            return redirect(url_for('laboratorio'))
        else:
            error = "Contrasena incorrecta"
    titulo = "Acceso a Campo" if destino == 'campo' else "Acceso a Laboratorio"
    return render_template_string(PAGINA_LOGIN, destino=destino, titulo=titulo, error=error)

@app.route('/salir')
def salir():
    session.clear()
    return redirect(url_for('portal'))

@app.route('/campo')
def campo():
    if not session.get('acceso_campo'):
        return redirect(url_for('login', destino='campo'))
    return render_template_string(PAGINA_CAMPO, lat=SITIO_LAT, lng=SITIO_LNG, sitio=SITIO_NOMBRE)

@app.route('/laboratorio')
def laboratorio():
    if not session.get('acceso_lab'):
        return redirect(url_for('login', destino='laboratorio'))
    return render_template_string(PAGINA_LAB, lat=ubicacion_actual["lat"], lng=ubicacion_actual["lng"], sitio=ubicacion_actual["nombre"])

@app.route('/api/datos')
def api_datos():
    return jsonify({"actual": ultimo_dato, "historial": historial})

@app.route('/escaneos')
def escaneos():
    disponibles = escaneos_disponibles()
    return render_template_string(
        PAGINA_ESCANEOS,
        especimenes={i: ESPECIMENES[i] for i in disponibles},
        hay=len(disponibles) > 0)


@app.route('/api/escaneo/<id_esp>')
def api_escaneo(id_esp):
    if id_esp not in ESPECIMENES:
        return jsonify({"puntos": [], "error": "Especimen desconocido"})
    return jsonify({"puntos": leer_escaneo(id_esp)})


@app.route('/api/riesgo')
def api_riesgo():
    return jsonify(calcular_riesgo())

@app.route('/api/ubicacion')
def api_ubicacion():
    return jsonify(ubicacion_actual)

@app.route('/api/ubicacion', methods=['POST'])
def guardar_ubicacion():
    # Solo campo (con sesion) puede cambiar la ubicacion
    if not session.get('acceso_campo'):
        return jsonify({"error": "no autorizado"}), 403
    datos = request.get_json(silent=True) or {}
    try:
        ubicacion_actual["lat"] = float(datos.get("lat"))
        ubicacion_actual["lng"] = float(datos.get("lng"))
        return jsonify({"ok": True, "ubicacion": ubicacion_actual})
    except (TypeError, ValueError):
        return jsonify({"error": "coordenadas invalidas"}), 400

@app.route('/descargar')
def descargar_csv():
    if os.path.exists(ARCHIVO_CSV):
        return send_file(ARCHIVO_CSV, as_attachment=True)
    return "Aun no hay datos registrados.", 404


ESTILOS = """
<style>
  :root { --crema:#fff3de; --verde:#bfdf96; --cafe:#724c3d; --cafe-claro:#a07060;
    --medio:#d4a855; --alerta:#a04030; --linea:#ddd0b0; --fondo-fila:#faefd4; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--crema); color:var(--cafe); font-family:Georgia,'Times New Roman',serif; min-height:100vh; }
  .topbar { background:var(--cafe); padding:10px 28px; display:flex; justify-content:space-between; align-items:center; }
  .topbar-titulo { color:var(--verde); font-family:'Courier New',monospace; font-size:11px; letter-spacing:0.22em; }
  .topbar-estado { display:flex; align-items:center; gap:7px; font-family:'Courier New',monospace; font-size:11px; color:var(--verde); }
  .punto { width:8px; height:8px; border-radius:50%; background:var(--verde); transition:background .3s; }
  .punto.offline { background:var(--alerta); }
  .link-salir { color:var(--verde); font-family:'Courier New',monospace; font-size:11px; text-decoration:none; opacity:0.8; }
  .link-salir:hover { opacity:1; }
</style>
"""

PAGINA_PORTAL = """
<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RexScan - Portal de Acceso</title>
""" + ESTILOS + """
<style>
  .portal-header { background:var(--cafe); text-align:center; padding:50px 20px 40px; border-bottom:3px solid var(--verde); }
  .portal-header .marca { color:var(--verde); font-family:'Courier New',monospace; font-size:14px; letter-spacing:0.3em; margin-bottom:12px; }
  .portal-header h1 { color:var(--crema); font-size:48px; font-weight:normal; }
  .portal-header p { color:var(--verde); font-family:'Courier New',monospace; font-size:15px; margin-top:10px; opacity:0.85; }
  .accesos { max-width:900px; margin:50px auto; padding:0 20px; display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:22px; }
  .acceso { background:var(--crema); border:2px solid var(--linea); border-radius:8px; padding:34px 26px; text-align:center; text-decoration:none; color:var(--cafe); transition:border-color .3s, transform .3s; display:block; }
  .acceso:hover { border-color:var(--verde); transform:translateY(-4px); }
  .acceso .icono { font-size:54px; margin-bottom:16px; }
  .acceso h2 { font-size:24px; margin-bottom:10px; }
  .acceso p { font-family:'Courier New',monospace; font-size:12px; opacity:0.7; line-height:1.5; }
  .acceso .tag { display:inline-block; margin-top:16px; font-family:'Courier New',monospace; font-size:11px; letter-spacing:0.1em; padding:4px 12px; border-radius:3px; }
  .tag.abierto { background:var(--verde); color:var(--cafe); }
  .tag.login { background:var(--medio); color:var(--crema); }
  footer.portal { text-align:center; padding:30px; color:var(--cafe); font-family:'Courier New',monospace; font-size:11px; opacity:0.5; }
</style></head><body>
<div class="topbar"><span class="topbar-titulo">REXSCAN - TECHREX</span><span class="topbar-titulo">SISTEMA DE PRESERVACION DE FOSILES</span></div>
<div class="portal-header">
  <div class="marca">TECNOLOGIA PARA EL FUTURO, DESCUBRIMIENTO DEL PASADO</div>
  <h1>RexScan</h1><p>Selecciona un modo de acceso</p>
</div>
<div class="accesos">
  <a class="acceso" href="/publico"><div class="icono">\U0001F3DB\uFE0F</div><h2>Museo Publico</h2><p>Explora los especimenes descubiertos y consulta al asistente sobre cada uno.</p><span class="tag abierto">ACCESO ABIERTO</span></a>
  <a class="acceso" href="/login/campo"><div class="icono">\u26CF\uFE0F</div><h2>Modo Campo</h2><p>Monitoreo en vivo del especimen y su entorno a pie de excavacion.</p><span class="tag login">REQUIERE CLAVE</span></a>
  <a class="acceso" href="/login/laboratorio"><div class="icono">\U0001F52C</div><h2>Laboratorio</h2><p>Analisis avanzado, estadisticas e historial completo de hallazgos.</p><span class="tag login">REQUIERE CLAVE</span></a>
  <a class="acceso" href="{{ url_escaner }}" target="_blank"><div class="icono">\U0001F4E1</div><h2>Escaneo 3D</h2><p>Reconstruccion digital del especimen por barrido laser.</p><span class="tag abierto">ACCESO ABIERTO</span></a>
</div>
<footer class="portal">RexScan - Equipo TechRex - Panama</footer>
</body></html>
"""

PAGINA_LOGIN = """
<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ titulo }} - RexScan</title>
""" + ESTILOS + """
<style>
  .login-wrap { max-width:400px; margin:80px auto; padding:0 20px; }
  .login-card { background:var(--crema); border:2px solid var(--linea); border-radius:8px; padding:40px 32px; text-align:center; }
  .login-card .icono { font-size:48px; margin-bottom:16px; }
  .login-card h1 { font-size:26px; margin-bottom:24px; }
  .login-card input { width:100%; padding:12px 14px; border:1px solid var(--linea); border-radius:4px; font-family:'Courier New',monospace; font-size:15px; margin-bottom:16px; background:#fff; }
  .login-card button { width:100%; padding:12px; background:var(--cafe); color:var(--verde); border:none; border-radius:4px; font-family:'Courier New',monospace; font-size:14px; letter-spacing:0.1em; cursor:pointer; transition:background .3s; }
  .login-card button:hover { background:var(--cafe-claro); }
  .error { color:var(--alerta); font-family:'Courier New',monospace; font-size:13px; margin-bottom:14px; }
  .volver { display:inline-block; margin-top:20px; color:var(--cafe); font-family:'Courier New',monospace; font-size:12px; opacity:0.6; text-decoration:none; }
</style></head><body>
<div class="topbar"><span class="topbar-titulo">REXSCAN - ACCESO</span><a class="link-salir" href="/">Volver al portal</a></div>
<div class="login-wrap"><div class="login-card">
  <div class="icono">{% if destino == 'campo' %}\u26CF\uFE0F{% else %}\U0001F52C{% endif %}</div>
  <h1>{{ titulo }}</h1>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST"><input type="password" name="clave" placeholder="Contrasena" autofocus><button type="submit">INGRESAR</button></form>
  <a class="volver" href="/">Cancelar</a>
</div></div></body></html>
"""

PAGINA_ESCANEOS = """<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RexScan - Archivo Digital 3D</title>
<style>
  :root { --crema:#fff3de; --verde:#bfdf96; --cafe:#724c3d; --cafe-claro:#a07060;
    --medio:#d4a855; --alerta:#a04030; --linea:#ddd0b0; --fondo-fila:#faefd4; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--crema); color:var(--cafe); font-family:Georgia,'Times New Roman',serif; min-height:100vh; }
  .topbar { background:var(--cafe); padding:10px 28px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
  .topbar-titulo { color:var(--verde); font-family:'Courier New',monospace; font-size:11px; letter-spacing:0.22em; }
  .link-salir { color:var(--linea); font-family:'Courier New',monospace; font-size:11px; letter-spacing:0.12em; text-decoration:none; }
  .link-salir:hover { color:var(--verde); }
  .contenido { max-width:1000px; margin:0 auto; padding:28px 20px 60px; }
  h1 { font-size:28px; font-weight:normal; margin-bottom:6px; }
  .subtitulo { font-family:'Courier New',monospace; font-size:12px; color:var(--cafe-claro); letter-spacing:0.1em; margin-bottom:8px; }
  .intro { font-size:15px; line-height:1.7; margin-bottom:24px; max-width:700px; }
  .selector { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:18px; }
  .sel-btn { background:var(--fondo-fila); border:1px solid var(--linea); color:var(--cafe); padding:10px 18px; border-radius:3px; font-family:'Courier New',monospace; font-size:12px; letter-spacing:0.08em; cursor:pointer; }
  .sel-btn:hover { border-color:var(--medio); }
  .sel-btn.activo { background:var(--cafe); color:var(--crema); border-color:var(--cafe); }
  .panel { display:grid; grid-template-columns:1fr 1fr; gap:18px; align-items:start; }
  @media (max-width:760px){ .panel { grid-template-columns:1fr; } }
  .lienzo-cont { background:var(--cafe); border-radius:4px; overflow:hidden; position:relative; }
  canvas { display:block; width:100%; height:380px; cursor:grab; }
  canvas:active { cursor:grabbing; }
  .hud { position:absolute; top:10px; left:12px; font-family:'Courier New',monospace; font-size:10px; color:var(--verde); letter-spacing:0.08em; line-height:1.6; pointer-events:none; }
  .ayuda { position:absolute; bottom:10px; right:12px; font-family:'Courier New',monospace; font-size:9px; color:var(--linea); letter-spacing:0.06em; pointer-events:none; }
  .foto-cont { background:var(--fondo-fila); border:1px solid var(--linea); border-radius:4px; overflow:hidden; }
  .foto-cont img { width:100%; height:380px; object-fit:cover; display:block; }
  .pie { font-family:'Courier New',monospace; font-size:10px; letter-spacing:0.12em; color:var(--cafe-claro); text-align:center; padding:8px; }
  .datos { margin-top:18px; }
  .fichas { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; }
  .ficha { background:var(--fondo-fila); border:1px solid var(--linea); border-radius:3px; padding:12px 14px; }
  .k { font-family:'Courier New',monospace; font-size:10px; letter-spacing:0.14em; color:var(--cafe-claro); }
  .v { font-size:19px; margin-top:5px; }
  .nota { background:var(--fondo-fila); border-left:3px solid var(--medio); padding:14px 18px; margin-top:22px; font-size:14px; line-height:1.65; }
  .vacio { background:var(--fondo-fila); border:1px dashed var(--linea); border-radius:4px; padding:40px 24px; text-align:center; }
  .vacio h2 { font-size:19px; font-weight:normal; margin-bottom:10px; }
  .vacio p { font-size:14px; line-height:1.7; color:var(--cafe-claro); max-width:520px; margin:0 auto; }
  code { background:var(--crema); padding:1px 6px; border-radius:2px; font-size:13px; }
</style></head><body>

<div class="topbar">
  <span class="topbar-titulo">REXSCAN - ARCHIVO DIGITAL 3D</span>
  <a class="link-salir" href="/publico">Volver al museo</a>
</div>

<div class="contenido">
  <h1>Archivo digital de especímenes</h1>
  <p class="subtitulo">RECONSTRUCCIONES POR BARRIDO LASER</p>
  <p class="intro">Cada pieza de la colección se digitaliza midiendo su superficie punto por
  punto con un sensor láser. El modelo resultante queda como registro permanente: aunque el
  fósil original se deteriore con el tiempo, su forma queda preservada y puede consultarse
  desde cualquier lugar.</p>

  {% if hay %}
  <div class="selector">
    {% for id, esp in especimenes.items() %}
    <button class="sel-btn" data-id="{{ id }}" data-img="{{ esp.imagen }}" onclick="elegir('{{ id }}')">{{ esp.nombre }}</button>
    {% endfor %}
  </div>

  <div class="panel">
    <div class="lienzo-cont">
      <canvas id="lienzo"></canvas>
      <div class="hud" id="hud">CARGANDO...</div>
      <div class="ayuda">ARRASTRA PARA ROTAR</div>
    </div>
    <div class="foto-cont">
      <img id="foto" src="" alt="Fotografia del especimen">
      <div class="pie">PIEZA FISICA</div>
    </div>
  </div>

  <div class="datos">
    <div class="fichas">
      <div class="ficha"><div class="k">PUNTOS MEDIDOS</div><div class="v" id="f-puntos">--</div></div>
      <div class="ficha"><div class="k">ALTURA</div><div class="v" id="f-alto">-- mm</div></div>
      <div class="ficha"><div class="k">ANCHO MAXIMO</div><div class="v" id="f-ancho">-- mm</div></div>
    </div>
  </div>

  <div class="nota">
    <strong>Sobre la reconstrucción:</strong> el sensor mide la distancia a la superficie con
    precisión aproximada de 1 mm mientras la pieza gira. Las zonas sin lectura válida quedan
    abiertas en el modelo: se muestra lo que se midió, sin rellenar lo que no se pudo ver.
  </div>
  {% else %}
  <div class="vacio">
    <h2>Todavía no hay escaneos en el archivo</h2>
    <p>Para añadir uno: realiza un escaneo en el módulo 3D, pulsa DESCARGAR PUNTOS,
    renombra el archivo con el código del espécimen (por ejemplo <code>ES-001.txt</code>)
    y colócalo en la carpeta <code>escaneos</code> junto al servidor.</p>
  </div>
  {% endif %}
</div>

<script>
const lienzo = document.getElementById('lienzo');
if (lienzo) {
const ctx = lienzo.getContext('2d');
let puntos = [], caras = [];
let rotY = 0.6, rotX = -0.3, zoom = 2.4;
let autoRotar = true, arrastrando = false, ultX = 0, ultY = 0;

function ajustarTamano(){
  const r = lienzo.getBoundingClientRect();
  lienzo.width = r.width * window.devicePixelRatio;
  lienzo.height = r.height * window.devicePixelRatio;
  ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
}
window.addEventListener('resize', ajustarTamano);
lienzo.addEventListener('mousedown', e => { arrastrando = true; autoRotar = false; ultX = e.clientX; ultY = e.clientY; });
window.addEventListener('mouseup', () => arrastrando = false);
window.addEventListener('mousemove', e => {
  if(!arrastrando) return;
  rotY += (e.clientX - ultX) * 0.01;
  rotX += (e.clientY - ultY) * 0.01;
  rotX = Math.max(-1.5, Math.min(1.5, rotX));
  ultX = e.clientX; ultY = e.clientY;
});
lienzo.addEventListener('wheel', e => {
  e.preventDefault();
  zoom *= (e.deltaY > 0) ? 0.92 : 1.08;
  zoom = Math.max(0.4, Math.min(14, zoom));
}, {passive:false});

window.elegir = async function(id){
  document.querySelectorAll('.sel-btn').forEach(b =>
    b.classList.toggle('activo', b.dataset.id === id));
  const btn = document.querySelector('.sel-btn[data-id="' + id + '"]');
  if(btn) document.getElementById('foto').src = btn.dataset.img;

  document.getElementById('hud').innerHTML = 'CARGANDO...';
  try {
    const res = await fetch('/api/escaneo/' + id);
    const d = await res.json();
    aplicar(d.puntos || []);
  } catch(e){
    document.getElementById('hud').innerHTML = 'ERROR AL CARGAR';
  }
};

function aplicar(crudos){
  if(!crudos.length){
    puntos = []; caras = [];
    document.getElementById('hud').innerHTML = 'SIN DATOS';
    return;
  }
  let cz = 0; crudos.forEach(p => cz += p[2]); cz /= crudos.length;
  puntos = crudos.map(p => ({x:p[0], y:p[1], z:p[2]-cz, fila:p[3], col:p[4]}));

  caras = [];
  const mapa = {};
  puntos.forEach(p => { mapa[p.fila + '_' + p.col] = p; });
  puntos.forEach(p => {
    const b = mapa[p.fila + '_' + (p.col+1)];
    const c = mapa[(p.fila+1) + '_' + (p.col+1)];
    const d = mapa[(p.fila+1) + '_' + p.col];
    if(b && c && d) caras.push([p, b, c, d]);
  });

  document.getElementById('f-puntos').textContent = puntos.length;
  const zs = crudos.map(p => p[2]);
  const alto = Math.max.apply(null, zs) - Math.min.apply(null, zs);
  const rr = crudos.map(p => Math.sqrt(p[0]*p[0] + p[1]*p[1]));
  document.getElementById('f-alto').textContent = alto.toFixed(1) + ' mm';
  document.getElementById('f-ancho').textContent = (Math.max.apply(null, rr)*2).toFixed(1) + ' mm';
  document.getElementById('hud').innerHTML = 'PUNTOS: ' + puntos.length + '<br>CARAS: ' + caras.length;
}

function proyectar(p, cx, cy, cosX, sinX, cosY, sinY){
  const x1 = p.x*cosY - p.y*sinY;
  const y1 = p.x*sinY + p.y*cosY;
  const y2 = y1*cosX - p.z*sinX;
  const z2 = y1*sinX + p.z*cosX;
  return {sx: cx + x1*zoom, sy: cy - z2*zoom, prof: y2};
}

function dibujar(){
  const w = lienzo.width/window.devicePixelRatio, h = lienzo.height/window.devicePixelRatio;
  ctx.clearRect(0,0,w,h);
  if(autoRotar) rotY += 0.006;
  const cx = w/2, cy = h/2;
  const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
  const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

  if(!puntos.length){
    ctx.fillStyle = 'rgba(191,223,150,0.5)';
    ctx.font = "11px 'Courier New', monospace";
    ctx.textAlign = 'center';
    ctx.fillText('SELECCIONA UN ESPECIMEN', cx, cy);
    requestAnimationFrame(dibujar); return;
  }

  if(caras.length){
    const lista = caras.map(ca => {
      const pr = ca.map(p => proyectar(p, cx, cy, cosX, sinX, cosY, sinY));
      const prof = (pr[0].prof+pr[1].prof+pr[2].prof+pr[3].prof)/4;
      const ux = pr[1].sx-pr[0].sx, uy = pr[1].sy-pr[0].sy;
      const vx = pr[3].sx-pr[0].sx, vy = pr[3].sy-pr[0].sy;
      return {pr:pr, prof:prof, area:Math.abs(ux*vy-uy*vx)/2};
    });
    lista.sort((a,b) => a.prof - b.prof);
    const ps = lista.map(c => c.prof);
    const mn = Math.min.apply(null,ps), mx = Math.max.apply(null,ps), rg = (mx-mn)||1;
    lista.forEach(c => {
      const t = (c.prof-mn)/rg;
      const luz = 0.32 + 0.68*(0.45*t + 0.55*Math.min(1, c.area/70));
      const col = 'rgb(' + Math.round(64+luz*168) + ',' + Math.round(52+luz*148) + ',' + Math.round(40+luz*78) + ')';
      ctx.beginPath();
      ctx.moveTo(c.pr[0].sx, c.pr[0].sy);
      ctx.lineTo(c.pr[1].sx, c.pr[1].sy);
      ctx.lineTo(c.pr[2].sx, c.pr[2].sy);
      ctx.lineTo(c.pr[3].sx, c.pr[3].sy);
      ctx.closePath();
      ctx.fillStyle = col; ctx.fill();
      ctx.strokeStyle = col; ctx.lineWidth = 0.7; ctx.stroke();
    });
  } else {
    const pr = puntos.map(p => proyectar(p, cx, cy, cosX, sinX, cosY, sinY));
    pr.sort((a,b) => a.prof - b.prof);
    pr.forEach(p => {
      ctx.fillStyle = 'rgba(191,223,150,0.8)';
      ctx.beginPath(); ctx.arc(p.sx, p.sy, 1.8, 0, Math.PI*2); ctx.fill();
    });
  }
  requestAnimationFrame(dibujar);
}

ajustarTamano();
dibujar();
const primero = document.querySelector('.sel-btn');
if(primero) elegir(primero.dataset.id);
}
</script>
</body></html>
"""


PAGINA_PUBLICA = """
<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Museo - Especimenes Descubiertos</title>
""" + ESTILOS + """
<style>
  header { background:var(--cafe); text-align:center; padding:40px 20px 32px; border-bottom:3px solid var(--verde); }
  header .eyebrow { color:var(--verde); font-family:'Courier New',monospace; font-size:13px; letter-spacing:0.25em; margin-bottom:10px; }
  header h1 { color:var(--crema); font-size:38px; font-weight:normal; }
  header p { color:var(--verde); font-family:'Courier New',monospace; font-size:14px; margin-top:8px; opacity:0.85; }
  .galeria { max-width:960px; margin:40px auto; padding:0 20px; display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:20px; }
  .card { background:var(--crema); border:1px solid var(--linea); border-radius:6px; overflow:hidden; text-decoration:none; color:var(--cafe); transition:border-color .3s, transform .3s; }
  .card:hover { border-color:var(--verde); transform:translateY(-3px); }
  .card-img { background:var(--cafe); text-align:center; padding:34px; font-size:64px; }
  .card-body { padding:18px 20px; }
  .card-body h2 { font-size:20px; margin-bottom:6px; }
  .card-body .periodo { font-family:'Courier New',monospace; font-size:12px; opacity:0.65; margin-bottom:12px; }
  .estado-badge { display:inline-block; font-family:'Courier New',monospace; font-size:11px; padding:3px 10px; border-radius:3px; letter-spacing:0.05em; }
  .estado-badge.Optimo { background:var(--verde); color:var(--cafe); }
  .estado-badge.Medio { background:var(--medio); color:var(--crema); }
  .ver { display:block; margin-top:14px; font-family:'Courier New',monospace; font-size:12px; color:var(--cafe-claro); }
</style></head><body>
<div class="topbar"><span class="topbar-titulo">REXSCAN - MUSEO PUBLICO</span><span><a class="link-salir" href="/escaneos">Archivo 3D</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a class="link-salir" href="/">Portal</a></span></div>
<header><div class="eyebrow">COLECCION DIGITAL</div><h1>Especimenes Descubiertos</h1><p>Explora cada hallazgo y consulta al asistente</p></header>
<div class="galeria">
  {% for id, esp in especimenes.items() %}
  <a class="card" href="/especimen/{{ id }}">
    <div class="card-img">{% if esp.imagen %}<img src="{{ esp.imagen }}" style="max-width:100%;max-height:120px;border-radius:4px;">{% else %}{{ esp.emoji }}{% endif %}</div>
    <div class="card-body"><h2>{{ esp.nombre }}</h2>
      <div class="periodo">{{ esp.periodo }} - {{ esp.edad }}</div>
      <span class="estado-badge {{ esp.estado }}">{{ esp.estado }}</span>
      <span class="ver">Ver detalle y preguntar</span>
    </div>
  </a>
  {% endfor %}
</div></body></html>
"""

PAGINA_DETALLE = """
<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ esp.nombre }} - RexScan</title>
""" + ESTILOS + """
<style>
  .detalle { max-width:800px; margin:30px auto; padding:0 20px; }
  .cabecera { background:var(--cafe); border-radius:8px; padding:30px; text-align:center; margin-bottom:24px; }
  .cabecera .emoji { font-size:80px; }
  .cabecera h1 { color:var(--crema); font-size:32px; font-weight:normal; margin-top:10px; }
  .cabecera .periodo { color:var(--verde); font-family:'Courier New',monospace; font-size:14px; margin-top:8px; }
  .datos { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:24px; }
  .dato { background:var(--crema); border:1px solid var(--linea); border-radius:5px; padding:16px; }
  .dato .k { font-family:'Courier New',monospace; font-size:11px; opacity:0.6; letter-spacing:0.1em; }
  .dato .v { font-size:16px; margin-top:6px; }
  .descripcion { background:var(--crema); border-left:4px solid var(--verde); padding:18px 20px; border-radius:0 5px 5px 0; margin-bottom:30px; line-height:1.6; }
  .asistente { background:var(--crema); border:1px solid var(--linea); border-radius:8px; overflow:hidden; }
  .asistente-head { background:var(--cafe); color:var(--verde); padding:14px 20px; font-family:'Courier New',monospace; font-size:13px; letter-spacing:0.1em; }
  .chat { padding:20px; min-height:120px; max-height:300px; overflow-y:auto; }
  .msg { margin-bottom:14px; display:flex; }
  .msg.ia { justify-content:flex-start; } .msg.user { justify-content:flex-end; }
  .burbuja { max-width:80%; padding:12px 16px; border-radius:12px; font-size:14px; line-height:1.5; }
  .msg.ia .burbuja { background:var(--fondo-fila); color:var(--cafe); border-bottom-left-radius:2px; }
  .msg.user .burbuja { background:var(--verde); color:var(--cafe); border-bottom-right-radius:2px; }
  .preguntas-btns { padding:16px 20px; border-top:1px solid var(--linea); display:flex; flex-wrap:wrap; gap:8px; }
  .preg-btn { background:#fff; border:1px solid var(--linea); border-radius:20px; padding:8px 14px; font-family:'Courier New',monospace; font-size:12px; color:var(--cafe); cursor:pointer; transition:all .2s; }
  .preg-btn:hover { background:var(--verde); border-color:var(--verde); }
  .volver { display:inline-block; margin:24px 0; color:var(--cafe); font-family:'Courier New',monospace; font-size:13px; text-decoration:none; opacity:0.7; }
</style></head><body>
<div class="topbar"><span class="topbar-titulo">REXSCAN - FICHA DE ESPECIMEN</span><a class="link-salir" href="/publico">Coleccion</a></div>
<div class="detalle">
  <div class="cabecera"><div class="emoji">{% if esp.imagen %}<img src="{{ esp.imagen }}" style="max-width:220px;max-height:200px;border-radius:8px;">{% else %}{{ esp.emoji }}{% endif %}</div><h1>{{ esp.nombre }}</h1><div class="periodo">{{ esp.periodo }} - {{ esp.edad }}</div></div>
  <div class="datos">
    <div class="dato"><div class="k">TIPO</div><div class="v">{{ esp.tipo }}</div></div>
    <div class="dato"><div class="k">ESTADO</div><div class="v">{{ esp.estado }}</div></div>
    <div class="dato"><div class="k">HALLADO EN</div><div class="v">{{ esp.lugar }}</div></div>
  </div>
  <div class="descripcion">{{ esp.descripcion }}</div>
  <div class="asistente">
    <div class="asistente-head">ASISTENTE REXSCAN - Pregunta sobre este especimen</div>
    <div class="chat" id="chat"><div class="msg ia"><div class="burbuja">Hola! Soy el asistente de RexScan. Toca una pregunta y te cuento sobre este especimen.</div></div></div>
    <div class="preguntas-btns" id="botones">
      {% for pregunta in esp.preguntas.keys() %}
      <button class="preg-btn" onclick="responder(this)" data-p="{{ pregunta }}">{{ pregunta }}</button>
      {% endfor %}
    </div>
  </div>
  <a class="volver" href="/publico">Volver a la coleccion</a>
</div>
<script>
  const respuestas = {
    {% for pregunta, resp in esp.preguntas.items() %}{{ pregunta|tojson }}: {{ resp|tojson }},
    {% endfor %}
  };
  function responder(btn){
    const pregunta = btn.dataset.p; const chat = document.getElementById('chat');
    chat.innerHTML += '<div class="msg user"><div class="burbuja">' + pregunta + '</div></div>';
    setTimeout(() => {
      chat.innerHTML += '<div class="msg ia"><div class="burbuja">' + respuestas[pregunta] + '</div></div>';
      chat.scrollTop = chat.scrollHeight;
    }, 400);
    chat.scrollTop = chat.scrollHeight;
  }
</script></body></html>
"""

PAGINA_CAMPO = """
<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Modo Campo - RexScan</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
""" + ESTILOS + """
<style>
  header { background:var(--cafe); padding:36px 28px 28px; text-align:center; border-bottom:3px solid var(--verde); }
  .eyebrow { color:var(--verde); font-family:'Courier New',monospace; font-size:14px; letter-spacing:0.25em; margin-bottom:10px; }
  header h1 { color:var(--crema); font-size:38px; font-weight:normal; margin-bottom:8px; }
  header p { color:var(--verde); font-family:'Courier New',monospace; font-size:15px; opacity:0.85; }
  .meta { display:flex; justify-content:center; gap:36px; margin-top:24px; flex-wrap:wrap; }
  .meta-label { color:var(--verde); font-family:'Courier New',monospace; font-size:13px; letter-spacing:0.15em; opacity:0.8; }
  .meta-valor { color:var(--crema); font-family:'Courier New',monospace; font-size:22px; margin-top:4px; }
  .meta-sep { width:1px; background:var(--verde); opacity:0.25; }
  .contenido { max-width:960px; margin:0 auto; padding:28px 20px 60px; }
  .alerta-banner { display:none; background:var(--medio); color:var(--crema); padding:14px 20px; border-radius:4px; margin-bottom:20px; font-family:'Courier New',monospace; font-size:15px; text-align:center; animation:pulso 1.5s infinite; }
  .alerta-banner.visible { display:block; }
  .alerta-banner.nivel-alerta { background:#c97a2e; }
  .alerta-banner.nivel-critico { background:var(--alerta); }
  @keyframes pulso { 0%,100%{opacity:1;} 50%{opacity:0.75;} }
  .seccion-label { font-family:'Courier New',monospace; font-size:18px; font-weight:bold; letter-spacing:0.2em; color:var(--cafe); border-bottom:2px solid var(--verde); padding-bottom:8px; margin:0 0 16px; }
  .fichas { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; margin-bottom:32px; }
  .ficha { background:var(--crema); border:1px solid var(--linea); border-radius:4px; padding:20px; position:relative; }
  .ficha.destacada { border:2px solid var(--verde); }
  .ficha-num { position:absolute; top:10px; right:14px; font-family:'Courier New',monospace; font-size:10px; color:var(--linea); }
  .ficha-label { font-family:'Courier New',monospace; font-size:14px; letter-spacing:0.12em; color:var(--cafe); opacity:0.65; margin-bottom:12px; }
  .ficha-valor { font-size:68px; color:var(--cafe); line-height:1; }
  .ficha-unidad { font-size:28px; opacity:0.55; }
  .ficha-sub { font-family:'Courier New',monospace; font-size:10px; color:var(--cafe); opacity:0.55; margin-top:8px; }
  .barra { height:5px; background:var(--linea); border-radius:3px; margin-top:12px; overflow:hidden; }
  .barra-relleno { height:100%; background:var(--verde); border-radius:3px; transition:width .6s ease; }
  .barra-relleno.alerta { background:var(--alerta); }
  .hueso-icono { font-size:52px; margin-bottom:6px; } .hueso-texto { font-size:34px; color:var(--cafe); }
  .hueso-sub { font-family:'Courier New',monospace; font-size:13px; color:var(--cafe); opacity:0.55; margin-top:6px; }
  .garra-icono { font-size:40px; margin-bottom:6px; } .garra-estado { font-size:22px; color:var(--cafe); margin-top:4px; }
  .etiqueta { display:inline-block; padding:10px 22px; border-radius:3px; font-family:'Courier New',monospace; font-size:24px; letter-spacing:0.06em; margin-top:4px; }
  .etiqueta.LIMPIO{background:var(--verde);color:var(--cafe);} .etiqueta.MEDIO{background:var(--medio);color:var(--crema);}
  .etiqueta.SUCIO{background:var(--alerta);color:var(--crema);} .etiqueta.SINHUESO{background:var(--linea);color:var(--cafe);}
  .etiqueta.NODETECTADO{background:var(--linea);color:var(--cafe);}
  .etiqueta.NIVEL-NORMAL{background:var(--verde);color:var(--cafe);} .etiqueta.NIVEL-PRECAUCION{background:var(--medio);color:var(--crema);}
  .etiqueta.NIVEL-ALERTA{background:#c97a2e;color:var(--crema);} .etiqueta.NIVEL-CRITICO{background:var(--alerta);color:var(--crema);}
  .grafica-cont { background:var(--crema); border:1px solid var(--linea); border-radius:4px; padding:20px; margin-bottom:32px; }
  svg.grafica { width:100%; height:100px; display:block; }
  .btn-descargar { display:inline-block; background:var(--cafe); color:var(--verde); text-decoration:none; padding:10px 22px; border-radius:4px; font-family:'Courier New',monospace; font-size:13px; letter-spacing:0.12em; margin-bottom:32px; }
  .btn-descargar:hover { background:var(--cafe-claro); }
  .mapa-cont { background:var(--crema); border:1px solid var(--linea); border-radius:4px; padding:8px; margin-bottom:32px; }
  #mapa { width:100%; height:320px; border-radius:4px; }
  .mapa-info { font-family:'Courier New',monospace; font-size:12px; color:var(--cafe); opacity:0.7; padding:10px 8px 4px; }
  .coord-editor { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:8px; }
  .coord-editor input { padding:8px 12px; border:1px solid var(--linea); border-radius:4px; font-family:'Courier New',monospace; font-size:13px; width:140px; background:#fff; }
  .coord-editor button { padding:8px 16px; background:var(--cafe); color:var(--verde); border:none; border-radius:4px; font-family:'Courier New',monospace; font-size:12px; letter-spacing:0.08em; cursor:pointer; }
  .coord-editor button:hover { background:var(--cafe-claro); }
  #guardar-msg { font-family:'Courier New',monospace; font-size:12px; color:#5a8a3a; }
  .tabla-cont { background:var(--crema); border:1px solid var(--linea); border-radius:4px; overflow:hidden; margin-bottom:32px; }
  table { width:100%; border-collapse:collapse; font-family:'Courier New',monospace; font-size:16px; }
  thead tr { background:var(--cafe); } thead th { color:var(--verde); padding:10px 14px; text-align:left; font-weight:normal; font-size:13px; }
  tbody tr { border-bottom:1px solid var(--linea); } tbody tr:nth-child(even){background:var(--fondo-fila);} tbody td{padding:12px 14px;}
  .badge { padding:3px 10px; border-radius:2px; font-size:13px; font-family:'Courier New',monospace; }
  .badge.LIMPIO{background:var(--verde);color:var(--cafe);} .badge.MEDIO{background:var(--medio);color:var(--crema);}
  .badge.SUCIO{background:var(--alerta);color:var(--crema);} .badge.SINHUESO{background:var(--linea);color:var(--cafe);}
  .badge.NODETECTADO{background:var(--linea);color:var(--cafe);}
</style></head><body>
<div class="topbar"><span class="topbar-titulo">REXSCAN - MODO CAMPO</span>
  <div class="topbar-estado"><span class="punto" id="punto"></span><span id="texto-conexion">Conectando...</span>&nbsp;-&nbsp;<a class="link-salir" href="/salir">Salir</a></div>
</div>
<header><p class="eyebrow">MONITOREO EN CAMPO</p><h1>Estado del Especimen</h1><p>Lectura continua del entorno a pie de excavacion</p>
  <div class="meta">
    <div><div class="meta-label">FECHA</div><div class="meta-valor" id="meta-fecha">--/--/----</div></div>
    <div class="meta-sep"></div><div><div class="meta-label">HORA</div><div class="meta-valor" id="meta-hora">--:--:--</div></div>
    <div class="meta-sep"></div><div><div class="meta-label">LECTURA</div><div class="meta-valor" id="meta-lectura">#---</div></div>
  </div>
</header>
<div class="contenido">
  <div class="alerta-banner" id="alerta-banner">Calculando riesgo...</div>
  <p class="seccion-label">ESTADO ACTUAL</p>
  <div class="fichas">
    <div class="ficha"><span class="ficha-num">01</span><div class="ficha-label">HUMEDAD DEL SEDIMENTO</div>
      <div class="ficha-valor" id="val-humedad">--<span class="ficha-unidad">%</span></div>
      <div class="barra"><div class="barra-relleno" id="barra" style="width:0%"></div></div>
      <div class="ficha-sub" id="val-raw">Valor raw: ---</div></div>
    <div class="ficha"><span class="ficha-num">02</span><div class="ficha-label">ESPECIMEN EN CAJA</div>
      <div class="hueso-icono" id="hueso-icono">\U0001F9B4</div><div class="hueso-texto" id="val-hueso">--</div>
      <div class="hueso-sub" id="hueso-sub">Sensor IR</div></div>
    <div class="ficha destacada"><span class="ficha-num">03</span><div class="ficha-label">ESTADO DE LIMPIEZA</div>
      <div id="val-estado"><span class="etiqueta SINHUESO">SIN DATOS</span></div>
      <div class="ficha-sub" id="val-id">HuskyLens ID: --</div></div>
    <div class="ficha"><span class="ficha-num">04</span><div class="ficha-label">SISTEMA DE MANIPULACION</div>
      <div class="garra-icono" id="garra-icono">\U0001F9BE</div><div class="garra-estado" id="val-garra">En reposo</div>
      <div class="ficha-sub">Garra automatica</div></div>
    <div class="ficha destacada"><span class="ficha-num">05</span><div class="ficha-label">RIESGO PREDICTIVO</div>
      <div id="val-riesgo"><span class="etiqueta SINHUESO">CALCULANDO</span></div>
      <div class="ficha-sub" id="val-riesgo-sub">Umbral: -- %</div></div>
  </div>
  <p class="seccion-label">TENDENCIA DE HUMEDAD</p>
  <div class="grafica-cont"><svg class="grafica" id="grafica" viewBox="0 0 600 100" preserveAspectRatio="none"></svg></div>
  <p class="seccion-label">HISTORIAL</p>
  <div class="tabla-cont"><table>
    <thead><tr><th>N.o</th><th>FECHA</th><th>HORA</th><th>HUMEDAD</th><th>ESPECIMEN</th><th>ESTADO</th></tr></thead>
    <tbody id="tabla-body"><tr><td colspan="6" style="text-align:center;opacity:0.5;padding:20px;">Esperando datos...</td></tr></tbody>
  </table></div>
  <p class="seccion-label">UBICACION DEL HALLAZGO</p>
  <div class="mapa-cont">
    <div class="mapa-info">Toca un punto del mapa o escribi las coordenadas para marcar el hallazgo.</div>
    <div class="coord-editor">
      <input type="text" id="in-lat" placeholder="Latitud" value="{{ lat }}">
      <input type="text" id="in-lng" placeholder="Longitud" value="{{ lng }}">
      <button id="btn-guardar" onclick="guardarUbicacion()">GUARDAR UBICACION</button>
      <span id="guardar-msg"></span>
    </div>
    <div id="mapa"></div>
  </div>
  <a href="/descargar" class="btn-descargar">DESCARGAR REGISTRO (CSV)</a>
</div>
<script>
// --- Mapa editable: marcar la ubicacion del hallazgo ---
let mLat = {{ lat }}, mLng = {{ lng }};
const mapa = L.map('mapa').setView([mLat, mLng], 15);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom:19, attribution:'&copy; OpenStreetMap' }).addTo(mapa);
let marcador = L.marker([mLat, mLng], {draggable:true}).addTo(mapa).bindPopup('Ubicacion del hallazgo').openPopup();

function ponerCoord(lat, lng){
  mLat = lat; mLng = lng;
  marcador.setLatLng([lat, lng]);
  document.getElementById('in-lat').value = lat.toFixed(6);
  document.getElementById('in-lng').value = lng.toFixed(6);
}
// Clic en el mapa
mapa.on('click', e => ponerCoord(e.latlng.lat, e.latlng.lng));
// Arrastrar el pin
marcador.on('dragend', e => { const p = e.target.getLatLng(); ponerCoord(p.lat, p.lng); });

function guardarUbicacion(){
  const lat = parseFloat(document.getElementById('in-lat').value);
  const lng = parseFloat(document.getElementById('in-lng').value);
  const msg = document.getElementById('guardar-msg');
  if (isNaN(lat) || isNaN(lng)){ msg.style.color='#a04030'; msg.textContent='Coordenadas invalidas'; return; }
  ponerCoord(lat, lng);
  fetch('/api/ubicacion', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({lat:lat, lng:lng})
  }).then(r => r.json()).then(d => {
    if (d.ok){ msg.style.color='#5a8a3a'; msg.textContent='Ubicacion guardada'; }
    else { msg.style.color='#a04030'; msg.textContent='Error al guardar'; }
    setTimeout(()=>{ msg.textContent=''; }, 2500);
  }).catch(()=>{ msg.style.color='#a04030'; msg.textContent='Sin conexion'; });
}

const tablaHistorial = []; const MAX_FILAS = 20;
let ultimoNivelRiesgo = 'NORMAL';
function claseEstado(e){ if(!e) return 'SINHUESO'; return e.replace(/ /g,''); }

const ETIQUETA_NIVEL = { NORMAL:'NORMAL', PRECAUCION:'PRECAUCION', ALERTA:'ALERTA', CRITICO:'CRITICO' };
async function actualizarRiesgo(){
  try {
    const res = await fetch('/api/riesgo'); const r = await res.json();
    ultimoNivelRiesgo = r.nivel;
    const banner = document.getElementById('alerta-banner');
    banner.classList.remove('nivel-alerta','nivel-critico');
    document.getElementById('val-riesgo').innerHTML = '<span class="etiqueta NIVEL-'+r.nivel+'">'+ETIQUETA_NIVEL[r.nivel]+'</span>';
    document.getElementById('val-riesgo-sub').textContent = 'Umbral: ' + r.umbral + '% (' + r.especimen + ')';
    if (r.nivel === 'CRITICO'){
      banner.classList.add('visible','nivel-critico');
      banner.textContent = 'HUMEDAD CRITICA - ' + r.especimen + ' supero el umbral de ' + r.umbral + '%';
    } else if (r.nivel === 'ALERTA'){
      banner.classList.add('visible','nivel-alerta');
      banner.textContent = 'RIESGO EN AUMENTO - ' + r.especimen + ' llegaria al umbral critico en ~' + r.minutos_estimados + ' min';
    } else if (r.nivel === 'PRECAUCION'){
      banner.classList.add('visible');
      banner.textContent = 'TENDENCIA A VIGILAR - ' + r.especimen + ' en ~' + r.minutos_estimados + ' min llegaria al umbral';
    } else {
      banner.classList.remove('visible');
    }
  } catch(e){}
}

async function actualizar(){
  try {
    const res = await fetch('/api/datos'); const data = await res.json();
    const d = data.actual; const hist = data.historial;
    document.getElementById('punto').classList.toggle('offline', !d.conectado);
    document.getElementById('texto-conexion').textContent = d.conectado ? 'Arduino conectado' : 'Sin conexion';
    document.getElementById('meta-fecha').textContent = d.fecha || '--/--/----';
    document.getElementById('meta-hora').textContent = d.hora || '--:--:--';
    document.getElementById('meta-lectura').textContent = '#' + String(d.lectura).padStart(3,'0');
    document.getElementById('val-humedad').innerHTML = d.humedad + '<span class="ficha-unidad">%</span>';
    document.getElementById('val-raw').textContent = 'Valor raw: ' + d.raw;
    const barra = document.getElementById('barra'); barra.style.width = d.humedad + '%';
    barra.classList.toggle('alerta', ultimoNivelRiesgo === 'ALERTA' || ultimoNivelRiesgo === 'CRITICO');
    document.getElementById('val-garra').textContent = d.hueso_presente === 'SI' ? 'Trasladando muestra' : 'En reposo';
    document.getElementById('garra-icono').textContent = d.hueso_presente === 'SI' ? '\U0001F9BE' : '\u2299';
    const hay = d.hueso_presente === 'SI';
    document.getElementById('hueso-icono').textContent = hay ? '\U0001F9B4' : '\u25CB';
    document.getElementById('val-hueso').textContent = hay ? 'Presente' : 'Ausente';
    document.getElementById('hueso-sub').textContent = hay ? 'IR detectado' : 'IR sin senal';
    const estado = (d.estado_suciedad || 'SIN HUESO').trim(); const clase = claseEstado(estado);
    document.getElementById('val-estado').innerHTML = '<span class="etiqueta '+clase+'">'+estado+'</span>';
    document.getElementById('val-id').textContent = 'HuskyLens ID: ' + (d.id_huskylens || '--');
    if (hist.length > 1){
      const W=600,H=100,PAD=8; const paso=(W-PAD*2)/(hist.length-1);
      const puntos=hist.map((p,i)=>{const x=PAD+i*paso;const y=H-PAD-(p.humedad/100)*(H-PAD*2);return x+','+y;}).join(' ');
      const y50=H-PAD-0.5*(H-PAD*2); const ultimo=hist[hist.length-1]; const yUlt=H-PAD-(ultimo.humedad/100)*(H-PAD*2);
      document.getElementById('grafica').innerHTML =
        '<line x1="0" y1="'+y50+'" x2="'+W+'" y2="'+y50+'" stroke="#bfdf96" stroke-width="0.8" stroke-dasharray="4 3"/>'+
        '<text x="4" y="'+(y50-3)+'" font-size="8" fill="#724c3d" font-family="Courier New" opacity="0.6">50%</text>'+
        '<polyline points="'+puntos+'" fill="none" stroke="#724c3d" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'+
        '<circle cx="'+(PAD+(hist.length-1)*paso)+'" cy="'+yUlt+'" r="4" fill="#bfdf96" stroke="#724c3d" stroke-width="1.5"/>';
    }
    if (d.lectura > 0 && (tablaHistorial.length===0 || tablaHistorial[0].lectura !== d.lectura)){
      tablaHistorial.unshift({lectura:d.lectura,fecha:d.fecha,hora:d.hora,humedad:d.humedad,hueso:d.hueso_presente,estado:estado,clase:clase});
      if (tablaHistorial.length > MAX_FILAS) tablaHistorial.pop();
      document.getElementById('tabla-body').innerHTML = tablaHistorial.map(r=>
        '<tr><td>#'+String(r.lectura).padStart(3,'0')+'</td><td>'+r.fecha+'</td><td>'+r.hora+'</td><td>'+r.humedad+'%</td>'+
        '<td style="color:'+(r.hueso==='SI'?'#5a8a3a':'#a04030')+'">'+(r.hueso==='SI'?'Presente':'Ausente')+'</td>'+
        '<td><span class="badge '+r.clase+'">'+r.estado+'</span></td></tr>').join('');
    }
  } catch(e){
    document.getElementById('punto').classList.add('offline');
    document.getElementById('texto-conexion').textContent = 'Servidor sin respuesta';
  }
}
setInterval(actualizar, 2000); actualizar();
setInterval(actualizarRiesgo, 2000); actualizarRiesgo();
</script></body></html>
"""

PAGINA_LAB = """
<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Laboratorio - RexScan</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
""" + ESTILOS + """
<style>
  header { background:var(--cafe); padding:34px 28px 26px; text-align:center; border-bottom:3px solid var(--verde); }
  .eyebrow { color:var(--verde); font-family:'Courier New',monospace; font-size:14px; letter-spacing:0.25em; margin-bottom:10px; }
  header h1 { color:var(--crema); font-size:36px; font-weight:normal; }
  header p { color:var(--verde); font-family:'Courier New',monospace; font-size:14px; opacity:0.85; margin-top:8px; }
  .contenido { max-width:1000px; margin:0 auto; padding:28px 20px 60px; }
  .alerta-banner { display:none; background:var(--medio); color:var(--crema); padding:14px 20px; border-radius:4px; margin-bottom:20px; font-family:'Courier New',monospace; font-size:15px; text-align:center; animation:pulso 1.5s infinite; }
  .alerta-banner.visible { display:block; }
  .alerta-banner.nivel-alerta { background:#c97a2e; }
  .alerta-banner.nivel-critico { background:var(--alerta); }
  @keyframes pulso { 0%,100%{opacity:1;} 50%{opacity:0.75;} }
  .seccion-label { font-family:'Courier New',monospace; font-size:17px; font-weight:bold; letter-spacing:0.2em; color:var(--cafe); border-bottom:2px solid var(--verde); padding-bottom:8px; margin:0 0 16px; }
  .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-bottom:32px; }
  .stat { background:var(--cafe); border-radius:6px; padding:22px; text-align:center; }
  .stat .num { color:var(--crema); font-size:44px; font-family:'Courier New',monospace; line-height:1; }
  .stat .lbl { color:var(--verde); font-family:'Courier New',monospace; font-size:12px; letter-spacing:0.1em; margin-top:8px; }
  .fichas { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:14px; margin-bottom:32px; }
  .ficha { background:var(--crema); border:1px solid var(--linea); border-radius:4px; padding:18px; }
  .ficha .k { font-family:'Courier New',monospace; font-size:11px; opacity:0.6; letter-spacing:0.1em; }
  .ficha .v { font-size:34px; margin-top:6px; color:var(--cafe); }
  .grafica-cont { background:var(--crema); border:1px solid var(--linea); border-radius:4px; padding:20px; margin-bottom:32px; }
  svg.grafica { width:100%; height:140px; display:block; }
  .tabla-cont { background:var(--crema); border:1px solid var(--linea); border-radius:4px; overflow:hidden; margin-bottom:24px; }
  table { width:100%; border-collapse:collapse; font-family:'Courier New',monospace; font-size:15px; }
  thead tr { background:var(--cafe); } thead th { color:var(--verde); padding:10px 14px; text-align:left; font-weight:normal; font-size:12px; }
  tbody tr { border-bottom:1px solid var(--linea); } tbody tr:nth-child(even){background:var(--fondo-fila);} tbody td{padding:10px 14px;}
  .btn-descargar { display:inline-block; background:var(--cafe); color:var(--verde); text-decoration:none; padding:10px 22px; border-radius:4px; font-family:'Courier New',monospace; font-size:13px; letter-spacing:0.12em; }
  .btn-descargar:hover { background:var(--cafe-claro); }
  .mapa-cont { background:var(--crema); border:1px solid var(--linea); border-radius:4px; padding:8px; margin-bottom:32px; }
  #mapa { width:100%; height:300px; border-radius:4px; }
  .mapa-info { font-family:'Courier New',monospace; font-size:12px; color:var(--cafe); opacity:0.7; padding:10px 8px; }
</style></head><body>
<div class="topbar"><span class="topbar-titulo">REXSCAN - LABORATORIO CENTRAL</span>
  <div class="topbar-estado"><span class="punto" id="punto"></span><span id="texto-conexion">Conectando...</span>&nbsp;-&nbsp;<a class="link-salir" href="/salir">Salir</a></div>
</div>
<header><p class="eyebrow">ANALISIS AVANZADO</p><h1>Laboratorio Central</h1><p>Estadisticas e historial completo de la sesion</p></header>
<div class="contenido">
  <div class="alerta-banner" id="alerta-banner">Calculando riesgo...</div>
  <p class="seccion-label">RESUMEN DE LA SESION</p>
  <div class="stats">
    <div class="stat"><div class="num" id="s-total">0</div><div class="lbl">LECTURAS TOTALES</div></div>
    <div class="stat"><div class="num" id="s-prom">--</div><div class="lbl">HUMEDAD PROMEDIO</div></div>
    <div class="stat"><div class="num" id="s-max">--</div><div class="lbl">HUMEDAD MAXIMA</div></div>
    <div class="stat"><div class="num" id="s-min">--</div><div class="lbl">HUMEDAD MINIMA</div></div>
  </div>
  <p class="seccion-label">ESTADO ACTUAL</p>
  <div class="fichas">
    <div class="ficha"><div class="k">HUMEDAD</div><div class="v" id="val-humedad">--%</div></div>
    <div class="ficha"><div class="k">ESPECIMEN</div><div class="v" id="val-hueso">--</div></div>
    <div class="ficha"><div class="k">ESTADO</div><div class="v" id="val-estado">--</div></div>
    <div class="ficha"><div class="k">HUSKYLENS ID</div><div class="v" id="val-id">--</div></div>
  </div>
  <p class="seccion-label">RIESGO PREDICTIVO</p>
  <div class="fichas">
    <div class="ficha"><div class="k">NIVEL DE RIESGO</div><div class="v" id="val-nivel">--</div></div>
    <div class="ficha"><div class="k">UMBRAL DEL ESPECIMEN</div><div class="v" id="val-umbral">--%</div></div>
    <div class="ficha"><div class="k">TIEMPO ESTIMADO A UMBRAL</div><div class="v" id="val-tiempo">--</div></div>
  </div>
  <p class="seccion-label">TENDENCIA DE HUMEDAD</p>
  <div class="grafica-cont"><svg class="grafica" id="grafica" viewBox="0 0 600 140" preserveAspectRatio="none"></svg></div>
  <p class="seccion-label">HISTORIAL COMPLETO</p>
  <div class="tabla-cont"><table>
    <thead><tr><th>N.o</th><th>HORA</th><th>HUMEDAD</th></tr></thead>
    <tbody id="tabla-body"><tr><td colspan="3" style="text-align:center;opacity:0.5;padding:20px;">Esperando datos...</td></tr></tbody>
  </table></div>
  <p class="seccion-label">UBICACION DEL HALLAZGO</p>
  <div class="mapa-cont">
    <div class="mapa-info" id="mapa-info">Ubicacion marcada desde campo</div>
    <div id="mapa"></div>
  </div>
  <a href="/descargar" class="btn-descargar">DESCARGAR REGISTRO COMPLETO (CSV)</a>
</div>
<script>
// --- Mapa de solo lectura: muestra la ubicacion marcada desde campo ---
const mapa = L.map('mapa', {scrollWheelZoom:false}).setView([{{ lat }}, {{ lng }}], 15);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom:19, attribution:'&copy; OpenStreetMap' }).addTo(mapa);
let marcadorLab = L.marker([{{ lat }}, {{ lng }}]).addTo(mapa).bindPopup('Ubicacion del hallazgo');
let ultLat = {{ lat }}, ultLng = {{ lng }};

async function actualizarUbicacion(){
  try {
    const r = await fetch('/api/ubicacion'); const u = await r.json();
    if (u.lat !== ultLat || u.lng !== ultLng){
      ultLat = u.lat; ultLng = u.lng;
      marcadorLab.setLatLng([u.lat, u.lng]);
      mapa.setView([u.lat, u.lng], 15);
      document.getElementById('mapa-info').textContent = 'Ubicacion marcada desde campo: ' + u.lat.toFixed(6) + ', ' + u.lng.toFixed(6);
    }
  } catch(e){}
}
setInterval(actualizarUbicacion, 3000); actualizarUbicacion();

const ETIQUETA_NIVEL = { NORMAL:'NORMAL', PRECAUCION:'PRECAUCION', ALERTA:'ALERTA', CRITICO:'CRITICO' };
async function actualizarRiesgo(){
  try {
    const res = await fetch('/api/riesgo'); const r = await res.json();
    const banner = document.getElementById('alerta-banner');
    banner.classList.remove('nivel-alerta','nivel-critico');
    document.getElementById('val-nivel').innerHTML = '<span style="font-size:22px;">'+ETIQUETA_NIVEL[r.nivel]+'</span>';
    document.getElementById('val-umbral').textContent = r.umbral + '%';
    document.getElementById('val-tiempo').textContent = r.minutos_estimados !== null ? ('~' + r.minutos_estimados + ' min') : '--';
    if (r.nivel === 'CRITICO'){
      banner.classList.add('visible','nivel-critico');
      banner.textContent = 'HUMEDAD CRITICA - ' + r.especimen + ' supero el umbral de ' + r.umbral + '%';
    } else if (r.nivel === 'ALERTA'){
      banner.classList.add('visible','nivel-alerta');
      banner.textContent = 'RIESGO EN AUMENTO - ' + r.especimen + ' llegaria al umbral critico en ~' + r.minutos_estimados + ' min';
    } else if (r.nivel === 'PRECAUCION'){
      banner.classList.add('visible');
      banner.textContent = 'TENDENCIA A VIGILAR - ' + r.especimen + ' en ~' + r.minutos_estimados + ' min llegaria al umbral';
    } else {
      banner.classList.remove('visible');
    }
  } catch(e){}
}

async function actualizar(){
  try {
    const res = await fetch('/api/datos'); const data = await res.json();
    const d = data.actual; const hist = data.historial;
    document.getElementById('punto').classList.toggle('offline', !d.conectado);
    document.getElementById('texto-conexion').textContent = d.conectado ? 'Arduino conectado' : 'Sin conexion';
    document.getElementById('val-humedad').textContent = d.humedad + '%';
    document.getElementById('val-hueso').textContent = d.hueso_presente === 'SI' ? 'Presente' : 'Ausente';
    document.getElementById('val-estado').textContent = (d.estado_suciedad || '--').trim();
    document.getElementById('val-id').textContent = d.id_huskylens || '--';
    if (hist.length > 0){
      const hums = hist.map(p=>p.humedad);
      document.getElementById('s-total').textContent = hist.length;
      document.getElementById('s-prom').textContent = Math.round(hums.reduce((a,b)=>a+b,0)/hist.length) + '%';
      document.getElementById('s-max').textContent = Math.max(...hums) + '%';
      document.getElementById('s-min').textContent = Math.min(...hums) + '%';
    }
    if (hist.length > 1){
      const W=600,H=140,PAD=10; const paso=(W-PAD*2)/(hist.length-1);
      const puntos=hist.map((p,i)=>{const x=PAD+i*paso;const y=H-PAD-(p.humedad/100)*(H-PAD*2);return x+','+y;}).join(' ');
      const y50=H-PAD-0.5*(H-PAD*2);
      document.getElementById('grafica').innerHTML =
        '<line x1="0" y1="'+y50+'" x2="'+W+'" y2="'+y50+'" stroke="#bfdf96" stroke-width="0.8" stroke-dasharray="4 3"/>'+
        '<text x="4" y="'+(y50-3)+'" font-size="9" fill="#724c3d" font-family="Courier New" opacity="0.6">50%</text>'+
        '<polyline points="'+puntos+'" fill="none" stroke="#724c3d" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
      document.getElementById('tabla-body').innerHTML = [...hist].reverse().map(p=>
        '<tr><td>#'+String(p.lectura||'').padStart(3,'0')+'</td><td>'+p.hora+'</td><td>'+p.humedad+'%</td></tr>').join('');
    }
  } catch(e){
    document.getElementById('punto').classList.add('offline');
    document.getElementById('texto-conexion').textContent = 'Servidor sin respuesta';
  }
}
setInterval(actualizar, 2000); actualizar();
setInterval(actualizarRiesgo, 2000); actualizarRiesgo();
</script></body></html>
"""


if __name__ == '__main__':
    ip = obtener_ip()
    print("=" * 54)
    print("  REXSCAN - TECHREX - Servidor iniciado")
    print("=" * 54)
    print(f"  En esta PC:    http://localhost:5000")
    print(f"  En el celular: http://{ip}:5000")
    print(f"  (Misma red WiFi)")
    print(f"  Clave campo:       {CLAVE_CAMPO}")
    print(f"  Clave laboratorio: {CLAVE_LABORATORIO}")
    print(f"  CSV guardandose en: {ARCHIVO_CSV}")
    print("=" * 54)
    hilo = threading.Thread(target=leer_arduino, daemon=True)
    hilo.start()
    app.run(host='0.0.0.0', port=5000, debug=False)
