/*
  Version 5 — Caja de Fosiles con flags de diagnostico
  ───────────────────────────────────────────────────────
  Misma base que caja_fosiles_v4_vertebras.ino, con dos interruptores
  booleanos agregados para poder desactivar HuskyLens y el sensor IR
  sin desconectar ningun cable.

  Se agrego porque el sensor IR estaba dando falsos positivos
  constantes ("hueso presente" todo el tiempo), lo cual disparaba al
  HuskyLens sin parar y eso corrompia la LCD por el cambio constante
  de velocidad del bus I2C. Con USAR_IR y USAR_HUSKYLENS en false se
  pudo aislar el problema: el sistema seguia funcionando (LCD, RTC,
  sensor de humedad) mientras se diagnosticaba el IR por separado.

  Para volver a activar todo una vez resuelto el sensor IR, solo hay
  que cambiar estas dos constantes a true — no hace falta tocar nada
  mas del codigo.
*/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <HUSKYLENS.h>
#include <RTClib.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);
HUSKYLENS huskylens;
RTC_DS3231 rtc;

#define SOIL_PIN A2
#define IR_PIN   5

const int VALOR_SECO   = 996;
const int VALOR_HUMEDO = 456;

// ── Interruptores de diagnostico ──────────────────
// Poner en false para desactivar temporalmente ese componente
// (util mientras se diagnostica un problema con otro sensor)
const bool USAR_HUSKYLENS = false;   // <- cambiar a true cuando se resuelva el IR
const bool USAR_IR        = false;   // <- cambiar a true cuando se resuelva el IR

const unsigned long INTERVALO_LECTURA  = 5UL * 1000UL;
const unsigned long INTERVALO_PANTALLA = 3UL * 1000UL;

unsigned long ultimaLectura  = 0;
unsigned long ultimoCambio   = 0;
unsigned long numeroLectura  = 0;
bool mostrarPantalla1 = true;

int  humedadActual = 0;
bool huesoActual   = false;
int  idDetectado   = 0;
String fechaActual = "";
String horaActual  = "";

void setup() {
  Serial.begin(9600);
  pinMode(IR_PIN, INPUT);
  Wire.begin();

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("RexScan         ");
  lcd.setCursor(0, 1);
  lcd.print("Iniciando...    ");

  if (!rtc.begin()) {
    lcd.setCursor(0, 1);
    lcd.print("Sin RTC!        ");
    delay(2000);
  }

  // ── HuskyLens ──────────────────────────────────
  if (USAR_HUSKYLENS) {
    int intentos = 0;
    while (!huskylens.begin(Wire) && intentos < 5) {
      lcd.setCursor(0, 1);
      lcd.print("Sin HuskyLens   ");
      delay(500);
      intentos++;
    }
  }

  // Forzar bus a 100kHz para que el LCD no se corrompa
  Wire.setClock(100000);

  delay(1500);

  lcd.setCursor(0, 0);
  lcd.print("                ");
  lcd.setCursor(0, 1);
  lcd.print("                ");

  Serial.println("Lectura,Fecha,Hora,Humedad_%,Valor_raw,Hueso_presente,ID_HuskyLens,Estado_suciedad");
}

void loop() {
  unsigned long ahora = millis();

  if (ahora - ultimaLectura >= INTERVALO_LECTURA) {
    ultimaLectura = ahora;
    numeroLectura++;

    int raw = analogRead(SOIL_PIN);
    humedadActual = map(raw, VALOR_SECO, VALOR_HUMEDO, 0, 100);
    humedadActual = constrain(humedadActual, 0, 100);

    // Sensor IR
    if (USAR_IR) {
      huesoActual = (digitalRead(IR_PIN) == LOW);
    } else {
      huesoActual = false;   // Simular "sin hueso" mientras el IR este desactivado
    }

    // HuskyLens — Object Classification
    idDetectado = 0;
    if (USAR_HUSKYLENS && huesoActual) {
      Wire.setClock(400000);   // HuskyLens necesita 400kHz
      if (huskylens.request()) {
        if (huskylens.available()) {
          HUSKYLENSResult result = huskylens.read();
          idDetectado = result.ID;
        }
      }
      Wire.setClock(100000);   // Volver a 100kHz para LCD y RTC
    }

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

String obtenerEstado(int id, bool hayHueso) {
  if (!hayHueso) return "SIN HUESO";
  if (id == 1)   return "Vertebra Caudal - LIMPIA";
  if (id == 2)   return "Vertebra Caudal - SUCIA";
  if (id == 3)   return "Vertebra Cervical Superior";
  if (id == 4)   return "Vertebra Cervical Inferior";
  return "NO DETECTADO";
}

void actualizarLCD() {
  lcd.setCursor(0, 0);
  lcd.print("                ");
  lcd.setCursor(0, 1);
  lcd.print("                ");

  if (mostrarPantalla1) {
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
      lcd.setCursor(0, 0);
      if (idDetectado == 2) {
        lcd.print("Estado: Sucia   ");
      } else {
        lcd.print("Estado: Limpia  ");
      }

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
