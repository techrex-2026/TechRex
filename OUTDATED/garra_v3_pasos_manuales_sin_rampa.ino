/*
  Version 3 — Secuencia manual de pasos, sin rampa
  ───────────────────────────────────────────────────
  Tercer intento: se abandono AccelStepper por completo y se paso a
  controlar las cuatro bobinas directamente, con un retardo fijo
  entre pasos (sin variar la velocidad durante el movimiento).

  Se descarto (parcialmente) porque un retardo fijo obligaba a
  elegir entre dos problemas: muy rapido (RETARDO bajo) y el motor
  perdia pasos en tramos con mas carga; muy lento (RETARDO alto) y
  el motor no tenia torque para arrancar desde parado — solo
  vibraba. La solucion final (garra/garra.ino) agrega una rampa:
  empieza lento y acelera en los primeros pasos, dandole al motor
  tiempo de tomar inercia antes de exigirle velocidad de crucero.

  Este archivo conserva la logica base de secuencia de bobinas que
  SI se mantuvo en la version final — lo que cambio fue agregar la
  rampa, no la forma de generar los pasos.
*/

const int IN1 = 3;
const int IN2 = 4;
const int IN3 = 5;
const int IN4 = 6;

const int RETARDO = 7;   // retardo fijo, sin rampa de arranque

void paso(int a, int b, int c, int d) {
  digitalWrite(IN1, a);
  digitalWrite(IN2, b);
  digitalWrite(IN3, c);
  digitalWrite(IN4, d);
  delay(RETARDO);
}

void setup() {
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
}

void loop() {
  paso(1, 0, 1, 0);
  paso(0, 1, 1, 0);
  paso(0, 1, 0, 1);
  paso(1, 0, 0, 1);
}
