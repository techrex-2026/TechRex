# Hardware notes

Stuff that broke and why, so we don't repeat it.

## Original Uno build

- **D8** — dead. Found because the L298N's LED cut out the moment
  this pin was wired in. Moved IN1 to D12 and moved on.

## Current Mega 2560

- **D22** — dead. Confirmed with a bare wire straight from the pin
  to GND: never read low, regardless of what was on the other end
  (button, switch, limit switch, or just touching the wire by hand).
- **D24** — same test, same result.
- **AREF/GND row (top edge)** — avoid entirely. AREF is tied to 5V
  internally, so anything switching that row to GND is a short, not
  a wiring mistake.

## L298N #1

Killed by running with the motor stalled and vibrating for too long
(coils mismatched with the step sequence in code). Multimeter check
afterward: OUT1 sat at 0.05V while OUT2/OUT3/OUT4 all read ~12V —
one channel gone. If it's buzzing instead of turning, kill power
inside 5 seconds. The vibration is what cooks the driver, not the
startup current.

## The "any button crashes the whole board" saga

Wasn't the button. Wasn't the switch. Wasn't the limit switch either
— three different components, identical symptom. Actual cause: a
stray four-space indent on `CLAVE_PUSH = "rexscan2026"` in
`Servidor_mapa.py` put it inside `descargar_csv()`, after its
returns, so it never ran — the variable didn't exist when
`recibir_datos()` needed it, and Flask crashed on every push. Nothing
to do with the claw hardware at all. If the same symptom survives
swapping the physical part twice, stop swapping parts.

## Motor speed / ramp

RETARDO=5 didn't skip steps but left almost no margin. RETARDO=15
had zero torque to start cold — pure buzz, no rotation. Fixed with a
ramp: start at 15, ease down to 7 over the first 50 steps. See
`garra/garra.ino`.

## VL53L1X (scanner)

I2C address scanner found it fine at 0x29, but `sensor.init()` kept
failing in the actual scan sketch. `Wire.setClock(400000)` was too
fast for the breadboard wiring — dropping to `Wire.setClock(100000)`
fixed initialization, scan just runs a bit slower.
