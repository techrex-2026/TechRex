/*
  TechRex — Garra robotica (Arduino Mega 2560)
  ─────────────────────────────────────────────
  Motor paso a paso NEMA 17 + L298N para el desplazamiento sobre riel,
  servo SG90 para abrir/cerrar la garra.

  ARQUITECTURA:
    - Movimiento del riel controlado por pasos manuales (secuencia de
      bobinas), no por AccelStepper, para tener control fino de la
      rampa de aceleracion y evitar la vibracion de arranque.
    - Rampa de aceleracion en los primeros pasos de cada movimiento,
      necesaria porque el L298N pierde ~2V y el motor no tiene torque
      suficiente para arrancar de golpe a velocidad de crucero.
    - Distancias calibradas en pasos por centimetro (PASOS_POR_CM),
      no en tiempo, para que el recorrido sea preciso.

  CONEXIONES:
    L298N   IN1 -> D3   IN2 -> D4   IN3 -> D5   IN4 -> D6
            GND -> GND de la Mega (tierra compartida obligatoria)
    Motor   verde+negro -> OUT1/OUT2 (una bobina)
            rojo+azul   -> OUT3/OUT4 (la otra bobina)
    Servo   señal -> D8
            rojo/negro -> alimentacion de la Mega (ver nota abajo)

  PINES EVITADOS (dañados durante el desarrollo, ver docs/hardware-notes.md):
    D8 en un Arduino Uno anterior, D22 y D24 en esta Mega, y toda la
    fila de AREF/GND del borde superior de la Mega.

  CALIBRACION:
    PASOS_POR_CM se calculo corriendo el motor 2 segundos y midiendo
    el avance real con una regla. Si cambias el RETARDO_FINAL, hay
    que volver a calibrar esa constante.
*/

#include <Servo.h>

// ── Pines ─────────────────────────────────────────
const int IN1 = 3;
const int IN2 = 4;
const int IN3 = 5;
const int IN4 = 6;
const int PIN_SERVO = 8;

// ── Velocidad y rampa ─────────────────────────────
// RETARDO_INICIAL: velocidad de arranque (mas lento = mas torque)
// RETARDO_FINAL:   velocidad de crucero, una vez tomada inercia
// PASOS_RAMPA:     cuantos pasos dura la transicion entre ambos
const int RETARDO_INICIAL = 15;
const int RETARDO_FINAL = 7;
const int PASOS_RAMPA = 50;

// Calibrado con RETARDO_FINAL = 7 (ver nota de calibracion arriba)
const float PASOS_POR_CM = 50.0;

// ── Posiciones del servo (microsegundos) ─────────
// Se uso writeMicroseconds en vez de write() porque el rango 0-180
// de write() no daba el recorrido completo que este servo permite.
const int SERVO_ABIERTO = 500;
const int SERVO_CERRADO = 2500;

Servo servoGarra;
int pasoActual = 0;

void avanzarPaso(bool derecha, int retardo) {
  int secuencia[4][4] = {
    {1,0,1,0},
    {0,1,1,0},
    {0,1,0,1},
    {1,0,0,1}
  };

  if (derecha) {
    pasoActual = (pasoActual + 1) % 4;
  } else {
    pasoActual = (pasoActual + 3) % 4;
  }

  digitalWrite(IN1, secuencia[pasoActual][0]);
  digitalWrite(IN2, secuencia[pasoActual][1]);
  digitalWrite(IN3, secuencia[pasoActual][2]);
  digitalWrite(IN4, secuencia[pasoActual][3]);
  delay(retardo);
}

void moverCm(float cm, bool derecha) {
  long pasosTotales = cm * PASOS_POR_CM;

  for (long i = 0; i < pasosTotales; i++) {
    int retardoActual;
    if (i < PASOS_RAMPA) {
      retardoActual = map(i, 0, PASOS_RAMPA, RETARDO_INICIAL, RETARDO_FINAL);
    } else {
      retardoActual = RETARDO_FINAL;
    }
    avanzarPaso(derecha, retardoActual);
  }
}

void apagarMotor() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

void secuencia() {
  servoGarra.writeMicroseconds(SERVO_ABIERTO);
  delay(1000);

  moverCm(13, true);         // derecha, hacia el especimen
  apagarMotor();

  servoGarra.writeMicroseconds(SERVO_CERRADO);
  delay(1000);

  moverCm(27, false);        // izquierda, de vuelta
  apagarMotor();

  servoGarra.writeMicroseconds(SERVO_ABIERTO);
  delay(1000);

  moverCm(16, true);         // derecha, posicion final
  apagarMotor();
}

void setup() {
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  // Da tiempo a que el L298N y el resto del sistema se estabilicen
  // antes de mover el motor.
  delay(2000);

  servoGarra.attach(PIN_SERVO);

  secuencia();
}

void loop() {
  // La secuencia corre una sola vez al encender.
  // Para repetirla: boton de reset fisico de la Mega.
}
