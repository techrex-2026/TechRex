"""
TechRex — Sincronizador local -> PythonAnywhere
─────────────────────────────────────────────────
El Arduino de campo esta conectado por USB (puerto serial) a esta
computadora, no por WiFi. PythonAnywhere corre en un servidor remoto
y no tiene forma de leer ese puerto COM directamente.

Este script resuelve eso: lee lo que el servidor local (Servidor_mapa.py,
puerto 5000) ya esta sirviendo, y lo reenvia por internet al servidor
de PythonAnywhere cada pocos segundos, para que cualquiera pueda ver
los datos en vivo desde afuera de la red local.

REQUIERE:
    - Servidor_mapa.py corriendo en esta misma PC (puerto 5000)
    - El endpoint /api/recibir_datos en Servidor_mapa_pythonanywhere.py
    - La misma CLAVE en ambos lados

USO:
    python empujar_datos.py

    Dejar corriendo en una terminal aparte durante toda la
    demostracion, junto a Servidor_mapa.py y servidor_escaner.py.
"""

import requests
import time

LOCAL = "http://127.0.0.1:5000/api/datos"
REMOTO = "https://techrex.pythonanywhere.com/api/recibir_datos"
CLAVE = "rexscan2026"   # debe coincidir con CLAVE_PUSH en el servidor remoto
INTERVALO_SEGUNDOS = 5

while True:
    try:
        datos = requests.get(LOCAL, timeout=3).json()
        datos["clave"] = CLAVE
        requests.post(REMOTO, json=datos, timeout=5)
        print("enviado:", datos["actual"].get("humedad", "?"), "%")
    except Exception as e:
        print("error:", e)
    time.sleep(INTERVALO_SEGUNDOS)
