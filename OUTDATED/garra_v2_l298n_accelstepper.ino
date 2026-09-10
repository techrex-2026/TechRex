/*
  Version 2 — L298N + AccelStepper
  ──────────────────────────────────
  Segundo intento, ya con el L298N (cuatro pines de control en vez
  de dos). Sigue usando AccelStepper para manejar velocidad y
  aceleracion.

  Se descarto porque el L298N pierde ~2V internamente y con la
  fuente de 12V/2A disponible no le quedaba torque suficiente para
  arrancar de golpe a la velocidad que pedia AccelStepper: el motor
  vibraba en vez de girar. Se reemplazo por control manual de la
  secuencia de bobinas con una rampa de aceleracion propia (ver
  garra/garra.ino), que da control fino sobre el arranque.

  Conexiones:
    IN1 -> D2   IN2 -> D3   IN3 -> D4   IN4 -> D5
    (el orden de pines varia entre iteraciones, revisar cada version
    especifica antes de reutilizar este cableado)
*/

#include <AccelStepper.h>

// IN1, IN3, IN2, IN4 (ese orden lo pide la libreria)
AccelStepper motor(AccelStepper::FULL4WIRE, 2, 4, 3, 5);

void setup() {
  motor.setMaxSpeed(300);
  motor.setAcceleration(150);
  motor.moveTo(200);
}

void loop() {
  motor.run();

  if (motor.distanceToGo() == 0) {
    delay(1000);
    motor.moveTo(-motor.currentPosition());
  }
}
