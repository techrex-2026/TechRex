/*
  Caja de Preservación de Fósiles — RexScan
  ─────────────────────────────────────────
  Sensores:
    - Sensor de humedad de suelo (A2)
    - Módulo IR de obstáculo (pin 4)
    - LCD HW-61 16x2 con I2C (0x27, A4/A5)
    - HuskyLens (I2C, A4/A5) — modo Object Classification
    - RTC HW-084 / DS3231 (I2C, A4/A5)

  Huesos entrenados en HuskyLens (modo Object Classification):
    ID 1 → Vértebra Caudal LIMPIA
    ID 2 → Vértebra Caudal SUCIA
    ID 3 → Vértebra Cervical Superior
    ID 4 → Vértebra Cervical Inferior

  Librerías necesarias:
    - LiquidCrystal_I2C (Frank de Brabander)
    - HUSKYLENS (DFRobot)
    - RTClib (Adafruit)

  Salida CSV para servidor web:
    Lectura, Fecha, Hora, Humedad_%, Valor_raw, Hueso_presente, ID_HuskyLens, Estado_suciedad
*/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <HUSKYLENS.h>
#include <RTClib.h>

// ── Dispositivos ──────────────────────────────────
LiquidCrystal_I2C lcd(0x27, 16, 2);
HUSKYLENS huskylens;
RTC_DS3231 rtc;

// ── Pines ─────────────────────────────────────────
#define SOIL_PIN A1
#define IR_PIN   5

// ── Calibración sensor de suelo ───────────────────
const int VALOR_SECO   = 1005;
const int VALOR_HUMEDO = 630;

// ── Temporización ────────────────────────────────
const unsigned long INTERVALO_LECTURA  = 5UL * 1000UL;
const unsigned long INTERVALO_PANTALLA = 3UL * 1000UL;

unsigned long ultimaLectura  = 0;
unsigned long ultimoCambio   = 0;
unsigned long numeroLectura  = 0;
bool mostrarPantalla1 = true;

// ── Variables compartidas ─────────────────────────
int  humedadActual = 0;
bool huesoActual   = false;
int  idDetectado   = 0;
String fechaActual = "";
String horaActual  = "";

void setup() {
  Serial.begin(9600);
  pinMode(IR_PIN, INPUT);
  Wire.begin();

  // ── LCD ────────────────────────────────────────
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("RexScan         ");
  lcd.setCursor(0, 1);
  lcd.print("Iniciando...    ");

  // ── RTC ────────────────────────────────────────
  if (!rtc.begin()) {
    lcd.setCursor(0, 1);
    lcd.print("Sin RTC!        ");
    delay(2000);
  }

   rtc.adjust(DateTime(F(__DATE__), F(__TIME__)) + TimeSpan(0, 0, 0, 7));

  // ── HuskyLens ──────────────────────────────────
  int intentos = 0;
  while (!huskylens.begin(Wire) && intentos < 5) {
    lcd.setCursor(0, 1);
    lcd.print("Sin HuskyLens   ");
    delay(500);
    intentos++;
  }

  // Forzar bus a 100kHz para que el LCD no se corrompa
  Wire.setClock(100000);
  Serial.print("HuskyLens conectada, intentos=");
  Serial.println(intentos);

  delay(1500);

  // Limpiar LCD
  lcd.setCursor(0, 0);
  lcd.print("                ");
  lcd.setCursor(0, 1);
  lcd.print("                ");

  // Encabezado CSV
  Serial.println("Lectura,Fecha,Hora,Humedad_%,Valor_raw,Hueso_presente,ID_HuskyLens,Estado_suciedad");
}

void loop() {
  unsigned long ahora = millis();

  if (ahora - ultimaLectura >= INTERVALO_LECTURA) {
    ultimaLectura = ahora;
    numeroLectura++;

    // Sensor de suelo
    int raw = analogRead(SOIL_PIN);
    humedadActual = map(raw, VALOR_SECO, VALOR_HUMEDO, 0, 100);
    humedadActual = constrain(humedadActual, 0, 100);

    // Sensor IR
    huesoActual = (digitalRead(IR_PIN) == LOW);

    // HuskyLens — Object Classification
    idDetectado = 0;
    if (huesoActual) {
      bool ok = huskylens.request();
      Serial.print("request()="); Serial.print(ok);
      Serial.print("  available()="); Serial.print(huskylens.available());
      if (ok && huskylens.available()) {
        HUSKYLENSResult result = huskylens.read();
        idDetectado = result.ID;
        Serial.print("  ID leido="); Serial.print(idDetectado);
      } else {
        Serial.print("  -> SIN RESPUESTA VALIDA");
      }
      Serial.println();
    }
    
    // RTC
    DateTime ahora_rtc = rtc.now();

    fechaActual = "";
    if (ahora_rtc.day() < 10)   fechaActual += "0";
    fechaActual += String(ahora_rtc.day())   + "/";
    if (ahora_rtc.month() < 10) fechaActual += "0";
    fechaActual += String(ahora_rtc.month()) + "/";
    fechaActual += String(ahora_rtc.year());

    horaActual = "";
    if (ahora_rtc.hour() < 10)   horaActual += "0";
    horaActual += String(ahora_rtc.hour())   + ":";
    if (ahora_rtc.minute() < 10) horaActual += "0";
    horaActual += String(ahora_rtc.minute()) + ":";
    if (ahora_rtc.second() < 10) horaActual += "0";
    horaActual += String(ahora_rtc.second());

    // Enviar CSV
    String estado = obtenerEstado(idDetectado, huesoActual);

    Serial.print(numeroLectura);   Serial.print(",");
    Serial.print(fechaActual);     Serial.print(",");
    Serial.print(horaActual);      Serial.print(",");
    Serial.print(humedadActual);   Serial.print(",");
    Serial.print(raw);             Serial.print(",");
    Serial.print(huesoActual ? "SI" : "NO"); Serial.print(",");
    Serial.print(idDetectado);     Serial.print(",");
    Serial.println(estado);
  }

  if (ahora - ultimoCambio >= INTERVALO_PANTALLA) {
    ultimoCambio = ahora;
    mostrarPantalla1 = !mostrarPantalla1;
    actualizarLCD();
  }
}

// ── Texto de estado según ID ──────────────────────
// Este texto es el que se envía por serie al servidor y aparece en la interfaz web.
String obtenerEstado(int id, bool hayHueso) {
  if (!hayHueso) return "SIN HUESO";
  if (id == 1)   return "Vertebra Caudal - LIMPIA";
  if (id == 2)   return "Vertebra Caudal - SUCIA";
  if (id == 3)   return "Vertebra Cervical Superior";
  if (id == 4)   return "Vertebra Cervical Inferior";
  return "NO DETECTADO";
}

// ── Dibujar LCD sin parpadeo ───────────────────────
void actualizarLCD() {
  lcd.setCursor(0, 0);
  lcd.print("                ");
  lcd.setCursor(0, 1);
  lcd.print("                ");

  if (mostrarPantalla1) {
    // Pantalla 1: Humedad + hueso + hora
    lcd.setCursor(0, 0);
    lcd.print("Hum:");
    lcd.print(humedadActual);
    lcd.print("% ");
    lcd.print(huesoActual ? "Hueso:SI" : "Hueso:NO");

    lcd.setCursor(0, 1);
    if (horaActual.length() > 0) {
      lcd.print(horaActual);
    } else {
      lcd.print("Lect #");
      lcd.print(numeroLectura);
    }

  } else {
    // Pantalla 2: Estado + Tipo del hueso
    if (!huesoActual) {
      lcd.setCursor(0, 0);
      lcd.print("Estado:         ");
      lcd.setCursor(0, 1);
      lcd.print("Sin hueso       ");
    } else if (idDetectado == 0) {
      lcd.setCursor(0, 0);
      lcd.print("Estado:         ");
      lcd.setCursor(0, 1);
      lcd.print("Analizando...   ");
    } else {
      // Línea 1: Estado (limpio o sucio)
      lcd.setCursor(0, 0);
      if (idDetectado == 2) {
        lcd.print("Estado: Sucia   ");
      } else {
        lcd.print("Estado: Limpia  ");
      }

      // Línea 2: Tipo de vértebra
      lcd.setCursor(0, 1);
      if (idDetectado == 1 || idDetectado == 2) {
        lcd.print("Tipo: V. Caudal ");
      } else if (idDetectado == 3) {
        lcd.print("Tipo: V. Cerv S ");
      } else if (idDetectado == 4) {
        lcd.print("Tipo: V. Cerv I ");
      } else {
        lcd.print("Tipo: ?         ");
      }
    }
  }
}
