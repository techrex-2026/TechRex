# TechRex — RexScan

Field-deployed assistant for fossil and bone-object excavation sites
— it doesn't dig, it's present on-site to make the work safer and
faster. Includes a stepper-driven claw on a rail, a laser 3D scanner
for specimens, and a Flask dashboard with live field monitoring.
Built for the TechRex competition (Sept 10, 2026).

## Quick start

### 1. Claw (Arduino Mega 2560)

```
cd garra
# Open garra.ino in the Arduino IDE, board = "Arduino Mega or Mega 2560"
# Upload with the motor and servo wired per the comments in the file
```

Hardware: NEMA 17 + L298N, SG90 servo.

### 2. Fossil box sensor (Arduino Uno)

```
cd caja
# Upload caja_fosiles.ino — soil humidity, IR bone detector,
# HuskyLens classification, RTC-stamped LCD display
```

Feeds `web/Servidor_mapa.py` over serial with CSV readings. See the
file header for wiring and the four trained specimen IDs.

Hardware: FC-28 soil sensor, IR obstacle module, HuskyLens, DS3231
RTC, 16x2 I2C LCD.

### 3. 3D scanner (Arduino Nano)

```
cd escaner
# Upload escaner_3d_rapidozigzag.ino to the Nano (COM5 by default)
python servidor_escaner.py    # -> http://localhost:5001
```

Hardware: VL53L1X laser sensor, two SG90 servos (turntable + arm).

### 4. Web dashboard (local)

```
cd web
python Servidor_mapa.py       # -> http://localhost:5000
```

Flask server: map (Leaflet.js), field humidity monitoring, and a
login portal for lab access.

### 5. Syncing with PythonAnywhere (optional)

There are **two separate server files**, not one:

- `web/Servidor_mapa.py` — local version. Reads the Arduino's serial
  port directly. This is the one you run on your machine.
- `web/Servidor_mapa_pythonanywhere.py` — the deployed version at
  `techrex.pythonanywhere.com`. Doesn't touch any serial port (no
  hardware access there); instead exposes `/api/recibir_datos`,
  which accepts data the local version already read.

To make the dashboard reachable off your local network during a
demo:

```
cd web
python empujar_datos.py
```

This reads from the local server (port 5000) and forwards it to the
PythonAnywhere copy every 5 seconds. Both sides share a key
(`CLAVE_PUSH` / `KEY`) — change it in both places if you change it
at all.

**On competition day**, update `IP_LOCAL_COMPETENCIA` inside
`Servidor_mapa_pythonanywhere.py` (and push that change to
PythonAnywhere) with the actual local IP of that network, so the
"Scan" button on the portal points at whichever machine has the
hardware plugged in.

## Layout

```
├── garra/              Claw firmware (Mega): stepper + servo
├── caja/               Fossil box sensor firmware (Uno): soil, IR, HuskyLens, LCD, RTC
├── escaner/            3D laser scanner (Nano) + its Flask server
├── web/                Dashboard, map, PythonAnywhere sync
├── docs/               Hardware notes, dead pins, calibration
└── OUTDATED/           Earlier versions of the claw code, kept for reference
```

## Docs

- `docs/hardware-notes.md` — burned-out pins, root causes behind the
  harder-to-diagnose failures, and calibration numbers. Worth
  reading before rewiring anything that stops working for no clear
  reason.

## Notes

- The claw motor runs manual step sequencing with an acceleration
  ramp, not `AccelStepper` — the L298N doesn't have the torque
  headroom on a 12V/2A supply to start at cruise speed cold.
- Page content served to end users (the field/lab dashboard UI)
  stays in Spanish — that's the audience at the actual competition.
  Only code comments and docs are in English.
