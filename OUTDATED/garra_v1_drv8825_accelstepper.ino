/*
  Version 1 — DRV8825 + AccelStepper
  ────────────────────────────────────
  Primer intento de mover el motor de la garra, antes de cambiar al
  L298N. Usa AccelStepper con velocidad y aceleracion configurables
  por software, y control fino de corriente por Vref en el driver.

  Se descarto porque para la version final se opto por el L298N
  (por disponibilidad de repuesto tras quemar el primer driver), y
  el L298N no soporta bien AccelStepper con esta carga — de ahi que
  el codigo final (garra/garra.ino) use secuencia manual de pasos
  con rampa en vez de esta libreria.

  Conexiones (DRV8825):
    STEP -> D3
    DIR  -> D4
    Motor: verde+negro -> A1/A2, rojo+azul -> B1/B2
    RESET y SLEEP puenteados entre si y a 5V
    Capacitor electrolitico 100-220uF/25V entre VMOT y GND, junto al driver
*/

#include <AccelStepper.h>

AccelStepper motor(AccelStepper::DRIVER, 3, 4);

void setup() {
  motor.setMaxSpeed(400);
  motor.setSpeed(200);
}

void loop() {
  motor.runSpeed();
}
