"""
RexScan — Servidor del modulo de escaneo 3D
───────────────────────────────────────────
Sirve el visor 3D y controla el escaner desde la propia pagina web.
Los puntos aparecen en pantalla mientras el robot escanea.

USO:
    1. Cierra el Monitor Serie del Arduino IDE (no pueden usar el puerto a la vez).
    2. Ejecuta:  python servidor_escaner.py
    3. Abre en el navegador la direccion que aparece en pantalla.
    4. Pulsa ESCANEAR AHORA.

Corre en el puerto 5001 para no chocar con el servidor principal (5000).

REQUISITOS:
    pip install flask pyserial
"""

from flask import Flask, jsonify, Response, request
import serial
import threading
import socket
import time

app = Flask(__name__)

# ── Configuracion ─────────────────────────────────
PUERTO_NANO   = 'COM5'    # cambialo si el Nano aparece en otro puerto
PUERTO_PORTAL = 5000      # puerto del servidor principal, para el enlace de vuelta
BAUDIOS       = 9600
TIEMPO_MAXIMO = 300       # segundos antes de cortar un escaneo colgado

# Columnas que produce una pasada. Debe coincidir con el sketch:
#   (ANGULO_FIN - ANGULO_INICIO) / PASO_ANGULO   ->  (180 - 0) / 10 = 18
# Se usa para encajar la segunda mitad a continuacion de la primera.
COLUMNAS_POR_PASADA = 18

# Filtro de picos: una medicion se descarta si su radio se aleja mas de este
# margen (en mm) del de sus dos vecinas en la misma fila. Las superficies
# reales cambian de forma gradual entre angulos contiguos; un salto brusco
# es una lectura mala, no relieve del especimen.
UMBRAL_PICO = 6.0

# ── Estado compartido entre el hilo de escaneo y la web ──
estado = {
    "activo": False,
    "terminado": False,
    "puntos": [],          # cada punto: [x, y, z, fila, columna]
    "mensaje": "Listo para escanear",
    "error": None,
    "pasada": 0            # 0 = ninguna, 1 = primera mitad, 2 = pieza completa
}
candado = threading.Lock()


def filtrar_picos(puntos, umbral=UMBRAL_PICO):
    """
    Elimina mediciones aisladas que se desvian de sus vecinas.

    El sensor falla ocasionalmente: capta un reflejo del fondo, del disco o
    del borde de la pieza, y devuelve una distancia que no corresponde a la
    superficie. En la malla esos valores aparecen como picos.

    Se compara el radio de cada punto con el de sus vecinos inmediatos en la
    misma fila. Si se aparta de AMBOS por mas del umbral, se descarta. Se
    exige que difiera de los dos para no borrar relieve real, que afecta a
    varios angulos seguidos y no a uno solo.
    """
    if not puntos:
        return []

    from math import hypot

    porCelda = {(p[3], p[4]): p for p in puntos}
    limpios = []

    for p in puntos:
        # Los puntos estimados no se filtran: no son lecturas del sensor
        if len(p) >= 6 and p[5] == 1:
            limpios.append(p)
            continue

        fila, col = p[3], p[4]
        radio = hypot(p[0], p[1])

        vecinos = []
        for dc in (-1, 1):
            v = porCelda.get((fila, col + dc))
            if v:
                vecinos.append(hypot(v[0], v[1]))

        # Sin vecinos con que comparar, se conserva la medicion
        if not vecinos:
            limpios.append(p)
            continue

        if all(abs(radio - rv) > umbral for rv in vecinos):
            continue   # se aparta de todos: es un pico

        limpios.append(p)

    return limpios


def reconstruir_por_simetria(puntos):
    """
    Completa la vuelta faltante reflejando la mitad medida.

    Cuando solo se dispone de una pasada (media vuelta), la cara opuesta
    del especimen queda sin datos. Esta funcion genera esa mitad aplicando
    una reflexion especular de los puntos medidos.

    IMPORTANTE: los puntos generados NO son mediciones. Se marcan con
    estimado=1 para que el visor los distinga visualmente y para que las
    dimensiones reportadas se calculen solo sobre lo realmente medido.
    El metodo asume simetria bilateral, supuesto que no siempre se cumple
    en material oseo: por eso la estimacion se declara, no se disimula.
    """
    if not puntos:
        return []

    medidos = [p for p in puntos if len(p) < 6 or p[5] == 0]
    if not medidos:
        return []

    cols = {p[4] for p in medidos}
    col_min, col_max = min(cols), max(cols)

    reflejados = []
    for p in medidos:
        x, y, z, fila, col = p[0], p[1], p[2], p[3], p[4]

        # Reflexion respecto al plano que contiene el eje de giro:
        # el angulo A pasa a ser -A, lo que en cartesianas invierte y.
        col_espejo = col_max + (col_max - col) + 1
        if col_espejo <= col_max:
            continue

        reflejados.append([x, -y, z, fila, col_espejo, 1])

    return reflejados


def hilo_escaneo(segunda_mitad=False):
    """
    Ejecuta un escaneo y acumula los puntos.

    El servo de la tornamesa solo cubre 180 grados, asi que la pieza se
    escanea en dos pasadas: la primera tal cual, y la segunda despues de
    voltear el especimen a mano sobre el disco.

    En la segunda pasada el especimen esta girado 180 grados respecto a
    la primera, de modo que lo que el sensor ve como angulo A corresponde
    en realidad al angulo A+180 de la pieza. Rotar los puntos 180 grados
    (x -> -x, y -> -y) los devuelve a su lugar real, y desplazar la
    columna encaja la malla a continuacion de la primera mitad.
    """
    global estado

    try:
        ser = serial.Serial(PUERTO_NANO, BAUDIOS, timeout=2)
    except serial.SerialException as e:
        with candado:
            estado["activo"] = False
            estado["terminado"] = True
            estado["error"] = (
                f"No se pudo abrir {PUERTO_NANO}. "
                "Revisa que el Monitor Serie del Arduino IDE este cerrado "
                "y que el Nano este conectado."
            )
            estado["mensaje"] = "Error de conexion"
        print(f"[escaner] error de puerto: {e}")
        return

    # El Nano se reinicia al abrir el puerto: hay que esperar su arranque
    time.sleep(2)
    ser.reset_input_buffer()
    ser.write(b'S')

    with candado:
        estado["mensaje"] = "Escaneando..."

    inicio = time.time()

    try:
        while True:
            if time.time() - inicio > TIEMPO_MAXIMO:
                with candado:
                    estado["mensaje"] = "Tiempo agotado"
                break

            linea = ser.readline().decode('utf-8', errors='ignore').strip()
            if not linea:
                continue

            if linea.startswith('SCAN_FIN'):
                with candado:
                    if segunda_mitad:
                        estado["pasada"] = 2
                        estado["mensaje"] = (
                            f"Pieza completa: {len(estado['puntos'])} puntos")
                    else:
                        estado["pasada"] = 1
                        estado["mensaje"] = (
                            f"Primera mitad lista: {len(estado['puntos'])} puntos. "
                            "Voltea el especimen 180 grados y escanea la segunda.")
                break

            if linea.startswith('SCAN_ABORTADO'):
                with candado:
                    estado["mensaje"] = "Escaneo abortado"
                break

            if linea.startswith('P,') or linea.startswith('p,'):
                partes = linea.split(',')
                if len(partes) >= 6:
                    try:
                        x, y = float(partes[1]), float(partes[2])
                        z    = float(partes[3])
                        fila, col = int(partes[4]), int(partes[5])

                        if segunda_mitad:
                            x, y = -x, -y
                            col = col + COLUMNAS_POR_PASADA

                        # El sexto campo distingue medicion (0) de estimacion (1)
                        punto = [x, y, z, fila, col, 0]
                        with candado:
                            estado["puntos"].append(punto)
                    except ValueError:
                        pass   # linea incompleta o cortada: se ignora

    except serial.SerialException:
        with candado:
            estado["error"] = "Se perdio la conexion con el Nano."
            estado["mensaje"] = "Conexion perdida"
    finally:
        ser.close()
        with candado:
            estado["activo"] = False
            estado["terminado"] = True


@app.route('/api/escanear', methods=['POST', 'GET'])
@app.route('/api/escanear/<modo>', methods=['POST', 'GET'])
def api_escanear(modo='nuevo'):
    segunda = (modo == 'segunda')

    with candado:
        if estado["activo"]:
            return jsonify({"ok": False, "mensaje": "Ya hay un escaneo en curso"})

        if segunda and not estado["puntos"]:
            return jsonify({"ok": False,
                            "mensaje": "Escanea primero la mitad inicial"})

        estado["activo"] = True
        estado["terminado"] = False
        estado["error"] = None
        if not segunda:
            estado["puntos"] = []      # la segunda pasada se suma a la primera
            estado["pasada"] = 0
        estado["mensaje"] = "Conectando con el Nano..."

    threading.Thread(target=hilo_escaneo, args=(segunda,), daemon=True).start()
    return jsonify({"ok": True})


@app.route('/api/estado')
def api_estado():
    # ?filtrar=0 devuelve las mediciones tal cual, para poder compararlas
    # ?simetria=1 completa la vuelta reflejando la mitad medida
    filtrar = request.args.get('filtrar', '1') != '0'
    simetria = request.args.get('simetria', '0') == '1'

    with candado:
        puntos = list(estado["puntos"])
        pasada = estado["pasada"]

    if filtrar:
        puntos = filtrar_picos(puntos)

    # La reconstruccion solo tiene sentido con una sola pasada:
    # con las dos mitades medidas no hay nada que estimar.
    estimados = 0
    if simetria and pasada == 1:
        reflejados = reconstruir_por_simetria(puntos)
        estimados = len(reflejados)
        puntos = puntos + reflejados

    with candado:
        return jsonify({
            "activo": estado["activo"],
            "terminado": estado["terminado"],
            "mensaje": estado["mensaje"],
            "error": estado["error"],
            "pasada": estado["pasada"],
            "descartados": max(0, len(estado["puntos"]) - (len(puntos) - estimados)),
            "estimados": estimados,
            "puntos": puntos
        })


@app.route('/')
def index():
    # Mismo host que la peticion, para que el enlace de vuelta funcione
    # tanto en esta PC como desde otro equipo de la red local.
    host = request.host.split(':')[0]
    pagina = PAGINA.replace("{{ url_portal }}", f"http://{host}:{PUERTO_PORTAL}/")
    return Response(pagina, mimetype='text/html')


PAGINA = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RexScan — Escaneo 3D</title>
<style>
  :root { --crema:#fff3de; --verde:#bfdf96; --cafe:#724c3d; --cafe-claro:#a07060;
    --medio:#d4a855; --alerta:#a04030; --linea:#ddd0b0; --fondo-fila:#faefd4; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--crema); color:var(--cafe); font-family:Georgia,'Times New Roman',serif; min-height:100vh; }
  .topbar { background:var(--cafe); padding:10px 28px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
  .topbar-titulo { color:var(--verde); font-family:'Courier New',monospace; font-size:11px; letter-spacing:0.22em; }
  .topbar-sub { color:var(--linea); font-family:'Courier New',monospace; font-size:10px; letter-spacing:0.15em; }
  .contenido { max-width:1000px; margin:0 auto; padding:24px 20px 60px; }
  h1 { font-size:26px; font-weight:normal; margin-bottom:4px; }
  .subtitulo { font-family:'Courier New',monospace; font-size:12px; color:var(--cafe-claro); letter-spacing:0.1em; margin-bottom:22px; }
  .seccion-label { font-family:'Courier New',monospace; font-size:15px; font-weight:bold; letter-spacing:0.2em; border-bottom:2px solid var(--verde); padding-bottom:8px; margin:26px 0 14px; }
  .lienzo-cont { background:var(--cafe); border-radius:4px; overflow:hidden; position:relative; }
  canvas { display:block; width:100%; height:460px; cursor:grab; }
  canvas:active { cursor:grabbing; }
  .hud { position:absolute; top:12px; left:14px; font-family:'Courier New',monospace; font-size:11px; color:var(--verde); letter-spacing:0.08em; line-height:1.7; pointer-events:none; }
  .ayuda { position:absolute; bottom:12px; right:14px; font-family:'Courier New',monospace; font-size:10px; color:var(--linea); letter-spacing:0.06em; pointer-events:none; }
  .modos { position:absolute; top:12px; right:14px; display:flex; gap:6px; }
  .leyenda { position:absolute; bottom:12px; left:14px; display:flex; gap:14px; font-family:'Courier New',monospace; font-size:10px; color:var(--linea); letter-spacing:0.06em; pointer-events:none; }
  .leyenda span { display:flex; align-items:center; gap:5px; }
  .leyenda i { width:11px; height:11px; border-radius:2px; display:inline-block; }
  .modo-btn { background:rgba(255,243,222,0.14); color:var(--linea); border:1px solid rgba(221,208,176,0.35); padding:6px 12px; border-radius:3px; font-family:'Courier New',monospace; font-size:10px; letter-spacing:0.1em; cursor:pointer; }
  .modo-btn.activo { background:var(--verde); color:var(--cafe); border-color:var(--verde); }
  .fila-botones { display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; align-items:center; }
  button.accion { background:var(--cafe); color:var(--crema); border:none; padding:13px 24px; border-radius:3px; font-family:'Courier New',monospace; font-size:13px; letter-spacing:0.14em; cursor:pointer; }
  button.accion:hover { background:var(--cafe-claro); }
  button.accion:disabled { background:var(--linea); color:var(--cafe-claro); cursor:default; }
  button.accion.sec { background:var(--medio); font-size:12px; padding:11px 18px; }
  .estado { font-family:'Courier New',monospace; font-size:12px; letter-spacing:0.08em; color:var(--cafe-claro); }
  .estado.error { color:var(--alerta); }
  .fichas { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-top:16px; }
  .ficha { background:var(--fondo-fila); border:1px solid var(--linea); border-radius:3px; padding:12px 14px; }
  .k { font-family:'Courier New',monospace; font-size:10px; letter-spacing:0.14em; color:var(--cafe-claro); }
  .v { font-size:21px; margin-top:5px; }
  .nota { background:var(--fondo-fila); border-left:3px solid var(--medio); padding:12px 16px; margin-top:18px; font-size:14px; line-height:1.6; }
</style>
</head>
<body>

<div class="topbar">
  <span class="topbar-titulo">REXSCAN — MODULO DE ESCANEO 3D</span>
  <span class="topbar-sub"><a href="{{ url_portal }}" style="color:var(--linea);text-decoration:none;">&larr; VOLVER AL PORTAL</a></span>
</div>

<div class="contenido">
  <h1>Reconstrucción digital del espécimen</h1>
  <p class="subtitulo">MEDICION LASER VL53L1X — COORDENADAS CILINDRICAS</p>

  <div class="fila-botones">
    <button class="accion" id="btn-escanear" onclick="iniciarEscaneo(false)">ESCANEAR 1ª MITAD</button>
    <button class="accion" id="btn-segunda" onclick="iniciarEscaneo(true)" disabled>ESCANEAR 2ª MITAD</button>
    <button class="accion sec" onclick="descargar()">DESCARGAR PUNTOS</button>
    <button class="accion sec" onclick="alternarRotacion()">PAUSAR / GIRAR</button>
    <label style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:0.08em;cursor:pointer;">
      <input type="checkbox" id="chk-filtro" checked onchange="refrescar()"> FILTRAR PICOS
    </label>
    <label style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:0.08em;cursor:pointer;">
      <input type="checkbox" id="chk-simetria" onchange="refrescar()"> RECONSTRUIR POR SIMETRIA
    </label>
    <span class="estado" id="estado">Listo para escanear</span>
    <span class="estado" id="descartes" style="color:var(--medio);"></span>
  </div>

  <div class="lienzo-cont" style="margin-top:16px;">
    <canvas id="lienzo"></canvas>
    <div class="hud" id="hud">SIN DATOS</div>
    <div class="modos">
      <button class="modo-btn activo" id="btn-malla" onclick="ponerModo('malla')">MALLA</button>
      <button class="modo-btn" id="btn-puntos" onclick="ponerModo('puntos')">PUNTOS</button>
    </div>
    <div class="ayuda">ARRASTRA PARA ROTAR — RUEDA PARA ACERCAR</div>
    <div class="leyenda" id="leyenda" style="display:none;">
      <span><i style="background:#c89a52;"></i>SUPERFICIE MEDIDA</span>
      <span><i style="background:#9aa2b4;opacity:0.6;"></i>ESTIMADA POR SIMETRIA</span>
    </div>
  </div>

  <div class="fichas">
    <div class="ficha"><div class="k">PUNTOS CAPTURADOS</div><div class="v" id="f-puntos">0</div></div>
    <div class="ficha"><div class="k">ALTURA DEL ESPECIMEN</div><div class="v" id="f-alto">-- mm</div></div>
    <div class="ficha"><div class="k">ANCHO MAXIMO</div><div class="v" id="f-ancho">-- mm</div></div>
  </div>

  <div class="nota">
    <strong>Sobre la reconstrucción:</strong> el sensor láser mide con precisión aproximada
    de 1 mm mediante tiempo de vuelo. La superficie se reconstruye uniendo mediciones
    vecinas del barrido; las zonas sin lectura válida quedan abiertas. Es una medición
    física real de profundidad, no una simulación.
    <br><br>
    <strong>Reconstrucción por simetría:</strong> el servo cubre 180 grados, de modo que la
    pieza completa requiere dos pasadas. Cuando solo hay una, esta opción estima la cara
    faltante reflejando la medida. La superficie estimada se dibuja en gris y las
    dimensiones reportadas se calculan únicamente sobre puntos medidos. El método asume
    simetría bilateral, supuesto que no siempre se cumple en material óseo: por eso la
    estimación se declara en pantalla en lugar de integrarse al modelo.
  </div>
</div>

<script>
const lienzo = document.getElementById('lienzo');
const ctx = lienzo.getContext('2d');

let puntos = [];
let caras = [];
let hayRejilla = false;
let modo = 'malla';
let sondeando = false;

let rotY = 0.6, rotX = -0.3, zoom = 2.6;
let autoRotar = true;
let arrastrando = false, ultX = 0, ultY = 0;

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

function alternarRotacion(){ autoRotar = !autoRotar; }

function ponerModo(m){
  modo = m;
  document.getElementById('btn-malla').classList.toggle('activo', m === 'malla');
  document.getElementById('btn-puntos').classList.toggle('activo', m === 'puntos');
}

// ── Control del escaneo ─────────────────────────
async function iniciarEscaneo(segunda){
  document.getElementById('btn-escanear').disabled = true;
  document.getElementById('btn-segunda').disabled = true;
  ponerEstado('Conectando con el Nano...', false);

  const ruta = segunda ? '/api/escanear/segunda' : '/api/escanear/nuevo';

  try {
    const res = await fetch(ruta, {method:'POST'});
    const r = await res.json();
    if(!r.ok){
      ponerEstado(r.mensaje, true);
      actualizarBotones(ultimaPasada);
      return;
    }
  } catch(e){
    ponerEstado('No se pudo contactar el servidor', true);
    actualizarBotones(ultimaPasada);
    return;
  }

  if(!sondeando){ sondeando = true; sondear(); }
}

let ultimaPasada = 0;

function actualizarBotones(pasada){
  ultimaPasada = pasada;
  document.getElementById('btn-escanear').disabled = false;
  // La segunda mitad solo tiene sentido con la primera ya capturada
  document.getElementById('btn-segunda').disabled = (pasada !== 1);
}

async function refrescar(){
  try {
    const s = await consultarEstado();
    if(!s) return;
    aplicar(s.puntos);
    mostrarDescartes(s.descartados, s.estimados);
  } catch(e){}
}

function mostrarDescartes(n, est){
  const leyenda = document.getElementById('leyenda');
  if(leyenda) leyenda.style.display = (est > 0) ? 'flex' : 'none';
  const el = document.getElementById('descartes');
  if(!el) return;
  const partes = [];
  if(n > 0) partes.push(n + ' picos descartados');
  if(est > 0) partes.push(est + ' puntos estimados por simetria');
  el.textContent = partes.join('  ·  ');
}

function consultarEstado(){
  const f = document.getElementById('chk-filtro').checked ? '1' : '0';
  const sim = document.getElementById('chk-simetria').checked ? '1' : '0';
  return fetch('/api/estado?filtrar=' + f + '&simetria=' + sim)
    .then(r => r.json())
    .catch(() => null);
}

async function sondear(){
  try {
    const res = await fetch('/api/estado?filtrar=' +
      (document.getElementById('chk-filtro').checked ? '1' : '0') +
      '&simetria=' +
      (document.getElementById('chk-simetria').checked ? '1' : '0'));
    const s = await res.json();

    ponerEstado(s.error ? s.error : s.mensaje, !!s.error);
    aplicar(s.puntos);
    mostrarDescartes(s.descartados, s.estimados);

    if(s.activo){
      setTimeout(sondear, 500);
      return;
    }
    actualizarBotones(s.pasada);
  } catch(e){
    ponerEstado('Se perdio contacto con el servidor', true);
    actualizarBotones(ultimaPasada);
  }

  sondeando = false;
}

function ponerEstado(txt, esError){
  const el = document.getElementById('estado');
  el.textContent = txt;
  el.classList.toggle('error', !!esError);
}

// ── Datos ───────────────────────────────────────
function aplicar(crudos){
  if(!crudos || crudos.length === 0) return;

  hayRejilla = crudos.every(p => p.length >= 5);

  let cz = 0;
  crudos.forEach(p => cz += p[2]);
  cz /= crudos.length;

  puntos = crudos.map(p => ({
    x: p[0], y: p[1], z: p[2] - cz,
    fila: p.length >= 5 ? p[3] : null,
    col:  p.length >= 5 ? p[4] : null,
    estimado: (p.length >= 6 && p[5] === 1)
  }));

  caras = [];
  if(hayRejilla) construirCaras();

  // Las dimensiones reportadas se calculan unicamente sobre puntos
  // medidos: un dato estimado no puede sustentar una medida.
  const reales = crudos.filter(p => !(p.length >= 6 && p[5] === 1));
  const base = reales.length ? reales : crudos;

  const nEst = crudos.length - reales.length;
  document.getElementById('f-puntos').textContent =
    nEst > 0 ? (reales.length + ' + ' + nEst + ' est.') : puntos.length;

  const zs = base.map(p => p[2]);
  const alto = Math.max.apply(null, zs) - Math.min.apply(null, zs);
  const radios = base.map(p => Math.sqrt(p[0]*p[0] + p[1]*p[1]));
  const ancho = Math.max.apply(null, radios) * 2;

  document.getElementById('f-alto').textContent = alto.toFixed(1) + ' mm';
  document.getElementById('f-ancho').textContent = ancho.toFixed(1) + ' mm';

  if(!hayRejilla) ponerModo('puntos');
  actualizarHud();
}

function construirCaras(){
  const mapa = {};
  puntos.forEach(p => { mapa[p.fila + '_' + p.col] = p; });

  puntos.forEach(p => {
    const a = p;
    const b = mapa[p.fila + '_' + (p.col + 1)];
    const c = mapa[(p.fila + 1) + '_' + (p.col + 1)];
    const d = mapa[(p.fila + 1) + '_' + p.col];
    if(a && b && c && d){
      const cara = [a, b, c, d];
      // Una cara es estimada si cualquiera de sus vertices lo es
      cara.estimada = a.estimado || b.estimado || c.estimado || d.estimado;
      caras.push(cara);
    }
  });
}

function actualizarHud(){
  const el = document.getElementById('hud');
  if(puntos.length === 0){ el.innerHTML = 'SIN DATOS'; return; }
  el.innerHTML = 'PUNTOS: ' + puntos.length +
    (hayRejilla ? '<br>CARAS: ' + caras.length : '<br>SIN REJILLA') +
    '<br>ROTACION: ' + (autoRotar ? 'AUTO' : 'MANUAL');
}

function descargar(){
  if(puntos.length === 0){ alert('No hay puntos que descargar.'); return; }
  let txt = 'SCAN_INICIO\\n';
  puntos.forEach(p => {
    txt += 'P,' + p.x.toFixed(2) + ',' + p.y.toFixed(2) + ',' + p.z.toFixed(2) +
           ',' + p.fila + ',' + p.col + '\\n';
  });
  txt += 'SCAN_FIN,' + puntos.length;

  const blob = new Blob([txt], {type:'text/plain'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'escaneo.txt';
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── Dibujo ──────────────────────────────────────
function proyectar(p, cx, cy, cosX, sinX, cosY, sinY){
  const x1 = p.x * cosY - p.y * sinY;
  const y1 = p.x * sinY + p.y * cosY;
  const y2 = y1 * cosX - p.z * sinX;
  const z2 = y1 * sinX + p.z * cosX;
  return {sx: cx + x1 * zoom, sy: cy - z2 * zoom, prof: y2};
}

function dibujar(){
  const w = lienzo.width / window.devicePixelRatio;
  const h = lienzo.height / window.devicePixelRatio;
  ctx.clearRect(0, 0, w, h);

  if(autoRotar) rotY += 0.006;

  const cx = w / 2, cy = h / 2;
  const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
  const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

  ctx.strokeStyle = 'rgba(221,208,176,0.20)';
  ctx.lineWidth = 1;
  const gz = -50;
  for(let g = -60; g <= 60; g += 20){
    linea3D({x:g, y:-60, z:gz}, {x:g, y:60, z:gz}, cx, cy, cosX, sinX, cosY, sinY);
    linea3D({x:-60, y:g, z:gz}, {x:60, y:g, z:gz}, cx, cy, cosX, sinX, cosY, sinY);
  }

  if(puntos.length === 0){
    ctx.fillStyle = 'rgba(191,223,150,0.55)';
    ctx.font = "12px 'Courier New', monospace";
    ctx.textAlign = 'center';
    ctx.fillText('SIN DATOS DE ESCANEO', cx, cy);
    ctx.fillText('PULSA ESCANEAR 1a MITAD PARA COMENZAR', cx, cy + 20);
    requestAnimationFrame(dibujar);
    return;
  }

  if(modo === 'malla' && caras.length > 0){
    dibujarMalla(cx, cy, cosX, sinX, cosY, sinY);
  } else {
    dibujarPuntos(cx, cy, cosX, sinX, cosY, sinY);
  }

  requestAnimationFrame(dibujar);
}

function dibujarMalla(cx, cy, cosX, sinX, cosY, sinY){
  const lista = caras.map(cara => {
    const pr = cara.map(p => proyectar(p, cx, cy, cosX, sinX, cosY, sinY));
    const prof = (pr[0].prof + pr[1].prof + pr[2].prof + pr[3].prof) / 4;
    const ux = pr[1].sx - pr[0].sx, uy = pr[1].sy - pr[0].sy;
    const vx = pr[3].sx - pr[0].sx, vy = pr[3].sy - pr[0].sy;
    const area = Math.abs(ux * vy - uy * vx) / 2;
    return {pr: pr, prof: prof, area: area};
  });

  lista.sort((a, b) => a.prof - b.prof);

  const profs = lista.map(c => c.prof);
  const minP = Math.min.apply(null, profs), maxP = Math.max.apply(null, profs);
  const rango = (maxP - minP) || 1;

  lista.forEach(c => {
    const t = (c.prof - minP) / rango;
    const inclinacion = Math.min(1, c.area / 90);
    const luz = 0.32 + 0.68 * (0.45 * t + 0.55 * inclinacion);

    // La superficie estimada se dibuja en gris azulado y translucida,
    // para que nunca se confunda con la superficie medida.
    let color;
    if(c.estimada){
      const v = Math.round(120 + luz * 90);
      color = 'rgba(' + v + ',' + (v + 8) + ',' + (v + 22) + ',0.45)';
    } else {
      const r = Math.round(64 + luz * 168);
      const g = Math.round(52 + luz * 148);
      const b = Math.round(40 + luz * 78);
      color = 'rgb(' + r + ',' + g + ',' + b + ')';
    }

    ctx.beginPath();
    ctx.moveTo(c.pr[0].sx, c.pr[0].sy);
    ctx.lineTo(c.pr[1].sx, c.pr[1].sy);
    ctx.lineTo(c.pr[2].sx, c.pr[2].sy);
    ctx.lineTo(c.pr[3].sx, c.pr[3].sy);
    ctx.closePath();

    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.7;
    ctx.stroke();
  });
}

function dibujarPuntos(cx, cy, cosX, sinX, cosY, sinY){
  const pr = puntos.map(p => {
    const q = proyectar(p, cx, cy, cosX, sinX, cosY, sinY);
    q.estimado = p.estimado;
    return q;
  });
  pr.sort((a, b) => a.prof - b.prof);

  const profs = pr.map(p => p.prof);
  const minP = Math.min.apply(null, profs), maxP = Math.max.apply(null, profs);
  const rango = (maxP - minP) || 1;

  pr.forEach(p => {
    const t = (p.prof - minP) / rango;
    const alpha = 0.26 + t * 0.74;
    const radio = 1.3 + t * 1.7;
    let r, g, b;
    if(p.estimado){
      r = 150; g = 158; b = 175;
    } else {
      r = Math.round(191 + t * 21);
      g = Math.round(223 - t * 55);
      b = Math.round(150 - t * 65);
    }
    ctx.fillStyle = 'rgba(' + r + ',' + g + ',' + b + ',' +
      (p.estimado ? (alpha * 0.55) : alpha).toFixed(2) + ')';
    ctx.beginPath();
    ctx.arc(p.sx, p.sy, radio, 0, Math.PI * 2);
    ctx.fill();
  });
}

function linea3D(a, b, cx, cy, cosX, sinX, cosY, sinY){
  const pa = proyectar(a, cx, cy, cosX, sinX, cosY, sinY);
  const pb = proyectar(b, cx, cy, cosX, sinX, cosY, sinY);
  ctx.beginPath();
  ctx.moveTo(pa.sx, pa.sy);
  ctx.lineTo(pb.sx, pb.sy);
  ctx.stroke();
}

setInterval(actualizarHud, 500);
ajustarTamano();
dibujar();
</script>
</body>
</html>
"""


def obtener_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == '__main__':
    ip = obtener_ip()
    print("=" * 52)
    print("  RexScan — Servidor del modulo de escaneo 3D")
    print("=" * 52)
    print(f"  Puerto del Nano : {PUERTO_NANO}")
    print(f"  En esta PC      : http://127.0.0.1:5001")
    print(f"  En la red local : http://{ip}:5001")
    print("=" * 52)
    print("  Cierra el Monitor Serie del Arduino IDE antes de escanear.")
    print()
    app.run(host='0.0.0.0', port=5001, debug=False)
