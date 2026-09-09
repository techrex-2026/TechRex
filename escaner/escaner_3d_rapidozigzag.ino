/*
  RexScan — Modulo de Escaneo 3D  (MODO RAPIDO — sensor laser VL53L1X)
  ────────────────────────────────────────────────────────────────────

  VARIANTE RAPIDA para demostracion en vivo: ~50 segundos por escaneo.
  Usa pasos de 10 grados y una sola medicion por punto.

  GEOMETRIA MEDIDA EN EL MONTAJE (ajustala si cambias el armado):
    brazo horizontal a 35 grados, brazo de 100 mm,
    sensor a 85 mm del eje de giro, disco a 45 mm de la base.
  Para el escaneo detallado (~6 min, mejor resolucion) usa la version
  escaner_3d_laser.ino, con pasos de 5 grados y mediana de 3 lecturas.

  Escaner de barrido cilindrico con sensor laser de tiempo de vuelo.

  PRINCIPIO:
    El especimen gira sobre una tornamesa (servo 1) mientras el sensor
    laser sube en pasos verticales (servo 2 con brazo).
    En cada cruce (angulo, altura) se mide la distancia al especimen.
    La distancia se convierte en radio -> se obtiene un punto 3D.

  POR QUE EL LASER Y NO EL ULTRASONICO:
    El HC-SR04 tiene un cono de deteccion de ~15 grados: "ve" borroso y
    promedia todo lo que hay dentro del cono. El VL53L1X mide con un haz
    estrecho y precision de ~1mm, asi que captura el contorno real de la
    pieza en lugar de su bulto aproximado.

  LIBRERIA NECESARIA:
    VL53L1X de Pololu
    (Arduino IDE -> Herramientas -> Administrar Bibliotecas -> "VL53L1X" -> Pololu)

  CONEXIONES:
    VL53L1X / TOF400C     SDA -> A4
                          SCL -> A5
                          VIN -> 5V (o 3.3V segun tu modulo)
                          GND -> GND
    Servo tornamesa  -> D9
    Servo brazo      -> D6
    IMPORTANTE: los servos con alimentacion externa de 5V y GND comun
    con el Arduino. Alimentarlos desde el Arduino provoca reinicios.

  USO:
    Enviar 'S' por el Monitor Serie para iniciar el escaneo.
    Enviar 'X' durante el escaneo para abortarlo.

  SALIDA:
    SCAN_INICIO
    P,x,y,z,fila,columna       <- un punto por linea, en milimetros
    SCAN_FIN,total_puntos
*/

#include <Wire.h>
#include <VL53L1X.h>
#include <Servo.h>

VL53L1X sensor;
Servo servoMesa;
Servo servoBrazo;

// ── Pines ─────────────────────────────────────────
#define SERVO_MESA_PIN  9
#define SERVO_BRAZO_PIN 6

// ── Parametros del escaneo ────────────────────────
// El SG90 cubre 0-180 grados. Para la vuelta completa se escanea 0-180,
// se voltea el especimen a mano, y se escanea de nuevo.
const int ANGULO_INICIO = 0;
const int ANGULO_FIN    = 180;
const int PASO_ANGULO   = 10;   // 19 columnas (modo rapido para demostracion)

// Columnas por fila, calculadas del rango y el paso
const int NUM_COLUMNAS = (ANGULO_FIN - ANGULO_INICIO) / PASO_ANGULO;

// ── Geometria del brazo ───────────────────────────
// BRAZO_HORIZONTAL: angulo en el que el brazo queda paralelo a la base.
//   Depende de como quedo encajada el aspa en el eje. MIDELO con el sketch
//   de prueba de servo antes de escanear.
// LONGITUD_BRAZO: del eje del servo a la cara del sensor, en mm.
const int   BRAZO_HORIZONTAL = 35;
const float LONGITUD_BRAZO   = 100.0;

// Recorrido: solo la franja donde esta el especimen. Barrer de mas
// solo produce filas vacias y alarga el escaneo sin aportar puntos.
const int BRAZO_INICIO = 25;
const int BRAZO_FIN    = 52;
const int PASO_BRAZO   = 2;     // 15 filas

// Distancia desde la cara del sensor hasta el eje de giro, en mm,
// MEDIDA CON EL BRAZO HORIZONTAL. De esto depende toda la geometria.
const float DISTANCIA_AL_EJE = 85.0;

// Radio maximo aceptado (mm). Valores mayores se descartan como fondo.
const float RADIO_MAXIMO = 45.0;

const int MEDICIONES_POR_PUNTO = 1;   // una sola lectura por punto (modo rapido)

// ── Estabilizacion mecanica ───────────────────────
const int ESPERA_BRAZO = 300;   // ms tras mover el brazo
const int ESPERA_MESA  = 100;   // ms tras mover la tornamesa

bool sensorOK = false;

void setup() {
  Serial.begin(9600);
  Wire.begin();
  Wire.setClock(400000);   // el VL53L1X trabaja bien a 400kHz

  servoMesa.attach(SERVO_MESA_PIN);
  servoBrazo.attach(SERVO_BRAZO_PIN);
  servoMesa.write(ANGULO_INICIO);
  servoBrazo.write(BRAZO_INICIO);

  sensor.setTimeout(500);
  if (!sensor.init()) {
    Serial.println(F("ERROR: no se detecta el sensor VL53L1X."));
    Serial.println(F("Revisa SDA en A4, SCL en A5, y la alimentacion."));
    sensorOK = false;
  } else {
    // Modo Short: alcance hasta ~1.3m, la mejor precision y la mayor
    // inmunidad a la luz ambiente. Ideal para escanear a 15cm.
    sensor.setDistanceMode(VL53L1X::Short);

    // HAZ ESTRECHO — la clave para escanear piezas pequenas.
    // Por defecto el sensor usa toda su matriz de 16x16 SPADs, lo que da un
    // campo de vision de ~27 grados: a 70mm de distancia "ve" un circulo de
    // 34mm, mas ancho que el especimen. Cada medicion promedia entonces el
    // hueso Y el fondo, produciendo radios erraticos y puntos descartados.
    // Con una region de interes de 4x4 el campo baja a ~7 grados: unos 9mm
    // a 70mm, mas fino que la pieza. Ese es el cambio que hace que el
    // escaneo mida el contorno real en lugar de un promedio borroso.
    sensor.setROISize(4, 4);

    sensor.setMeasurementTimingBudget(50000);   // 50ms por medicion
    sensor.startContinuous(50);
    sensorOK = true;
    Serial.println(F("RexScan - Modulo de escaneo 3D listo (VL53L1X)"));
  }

  Serial.println(F("Envia 'S' para iniciar el escaneo."));
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if ((c == 'S' || c == 's') && sensorOK) {
      ejecutarEscaneo();
    } else if ((c == 'S' || c == 's') && !sensorOK) {
      Serial.println(F("Sin sensor: no se puede escanear."));
    }
  }
}

// ── Medicion ─────────────────────────────────────
// Devuelve la distancia en mm, o -1 si la lectura no es valida.
float medirDistancia() {
  uint16_t mm = sensor.read();
  if (sensor.timeoutOccurred()) return -1;

  // El VL53L1X informa el estado de cada medicion.
  // 0 = valida. Cualquier otro codigo indica una lectura poco fiable.
  if (sensor.ranging_data.range_status != VL53L1X::RangeValid) return -1;

  if (mm < 40 || mm > 1300) return -1;   // fuera del rango util (min ~40mm)
  return (float)mm;
}

// Mediana de varias mediciones, para filtrar lecturas erraticas
float medirEstable() {
  float v[MEDICIONES_POR_PUNTO];
  int validas = 0;

  for (int i = 0; i < MEDICIONES_POR_PUNTO; i++) {
    float m = medirDistancia();
    if (m > 0) { v[validas] = m; validas++; }
    if (MEDICIONES_POR_PUNTO > 1) delay(60);
  }

  if (validas == 0) return -1;

  for (int i = 0; i < validas - 1; i++) {
    for (int j = i + 1; j < validas; j++) {
      if (v[j] < v[i]) { float t = v[i]; v[i] = v[j]; v[j] = t; }
    }
  }
  return v[validas / 2];
}

// ── Movimiento gradual ───────────────────────────
// Devuelve un servo a su posicion de reposo poco a poco.
// Un salto grande de golpe sacude la estructura y puede tumbar
// el especimen justo antes de la segunda pasada.
void moverSuave(Servo &s, int desde, int hasta) {
  int paso = (hasta > desde) ? 1 : -1;
  for (int p = desde; p != hasta; p += paso) {
    s.write(p);
    delay(8);
  }
  s.write(hasta);
}

// ── Escaneo completo ─────────────────────────────
void ejecutarEscaneo() {
  long totalPuntos = 0;
  int fila = 0;

  Serial.println(F("SCAN_INICIO"));

  for (int b = BRAZO_INICIO; b <= BRAZO_FIN; b += PASO_BRAZO) {
    servoBrazo.write(b);
    delay(ESPERA_BRAZO);

    // Geometria del brazo en esta fila.
    // El brazo gira, no sube en linea recta: al inclinarse, el sensor
    // sube (o baja) PERO tambien retrocede, alejandose del eje de giro.
    // Ambos efectos se calculan a partir del angulo y se corrigen aqui.
    float alfa = (b - BRAZO_HORIZONTAL) * 3.14159265 / 180.0;
    float z = LONGITUD_BRAZO * sin(alfa);
    float distanciaEje = DISTANCIA_AL_EJE + LONGITUD_BRAZO * (1.0 - cos(alfa));

    // BARRIDO EN ZIGZAG.
    // Si cada fila empezara siempre en 0 grados, al terminar la anterior la
    // tornamesa tendria que volver de 180 a 0 de un golpe: una sacudida que
    // desplaza o tumba el especimen. Recorriendo las filas pares hacia
    // adelante y las impares hacia atras, la mesa nunca da ese salto.
    bool haciaAdelante = (fila % 2 == 0);

    for (int paso = 0; paso <= NUM_COLUMNAS; paso++) {
      int columna = haciaAdelante ? paso : (NUM_COLUMNAS - paso);
      int a = ANGULO_INICIO + columna * PASO_ANGULO;
      // Permitir abortar a mitad del escaneo
      if (Serial.available()) {
        char c = Serial.read();
        if (c == 'X' || c == 'x') {
          Serial.println(F("SCAN_ABORTADO"));
          moverSuave(servoMesa, a, ANGULO_INICIO);
          moverSuave(servoBrazo, b, BRAZO_INICIO);
          return;
        }
      }

      servoMesa.write(a);
      delay(ESPERA_MESA);

      float d = medirEstable();

      if (d > 0) {
        // La distancia medida llega al borde del especimen.
        // El radio es cuanto sobresale respecto al eje de giro.
        float radio = distanciaEje - d;

        if (radio > 2.0 && radio <= RADIO_MAXIMO) {
          float rad = a * 3.14159265 / 180.0;
          float x = radio * cos(rad);
          float y = radio * sin(rad);

          Serial.print(F("P,"));
          Serial.print(x, 2);      Serial.print(',');
          Serial.print(y, 2);      Serial.print(',');
          Serial.print(z, 2);      Serial.print(',');
          Serial.print(fila);      Serial.print(',');
          Serial.println(columna);

          totalPuntos++;
        }
      }

    }

    fila++;
  }

  // Volver al reposo sin sacudir la estructura
  int ultimoAngulo = ((fila - 1) % 2 == 0) ? ANGULO_FIN : ANGULO_INICIO;
  moverSuave(servoMesa, ultimoAngulo, ANGULO_INICIO);
  moverSuave(servoBrazo, BRAZO_FIN, BRAZO_INICIO);

  Serial.print(F("SCAN_FIN,"));
  Serial.println(totalPuntos);
}
