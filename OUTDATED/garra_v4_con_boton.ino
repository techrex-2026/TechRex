/*
  Version 4 — Disparo con boton (D22)
  ──────────────────────────────────────
  Version que disparaba toda la secuencia con un pulsador conectado
  a D22, en vez de correrla sola al encender.

  Se descarto para la demostracion final porque, sin importar el
  componente probado (pulsador comun, pulsador de arcade, switch,
  final de carrera, o incluso un cable tocado a mano contra GND), el
  mismo circuito apagaba la Mega entera al cerrarse. La causa real
  no tenia nada que ver con el boton ni con el hardware de la garra:
  era un error de indentacion en Servidor_mapa.py (la linea
  CLAVE_PUSH quedo metida dentro de otra funcion y nunca se
  ejecutaba), que hacia crashear el servidor de Flask en
  PythonAnywhere. Ver docs/hardware-notes.md para el detalle.

  Se volvio a la version mas simple: correr la secuencia una sola
  vez dentro de setup() al encender (ver garra/garra.ino), evitando
  por completo la necesidad de un pin de disparo externo para el dia
  de la competencia. Este archivo se conserva porque el patron de
  usar un boton es razonable y se podria retomar si se resuelve
  correctamente el cableado del pin de disparo.
*/

#include <AccelStepper.h>
#include <Servo.h>

// IN1=3, IN3=5, IN2=4, IN4=6
AccelStepper motor(AccelStepper::FULL4WIRE, 3, 5, 4, 6);
Servo servoGarra;

const int PIN_SERVO = 9;
const int PIN_BOTON = 22;   // pin que resulto danado en esta Mega
const unsigned long DURACION = 2000;
const float VELOCIDAD = 300;

void moverMotor(float velocidad, unsigned long duracion) {
  motor.setSpeed(velocidad);
  unsigned long inicio = millis();
  while (millis() - inicio < duracion) {
    motor.runSpeed();
  }
}

void secuencia() {
  servoGarra.write(180);
  delay(1000);
  delay(5000);

  moverMotor(VELOCIDAD, DURACION);

  servoGarra.write(0);
  delay(1000);

  moverMotor(-VELOCIDAD, DURACION);
}

void setup() {
  pinMode(PIN_BOTON, INPUT_PULLUP);

  servoGarra.attach(PIN_SERVO);
  servoGarra.write(0);
  delay(1000);

  motor.setMaxSpeed(VELOCIDAD);
}

void loop() {
  if (digitalRead(PIN_BOTON) == LOW) {
    secuencia();
    delay(500);
  }
}
