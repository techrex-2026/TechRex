# Retired code

Two separate progressions kept here, each with its own numbering.
Every file's header explains what it tried and why it was replaced.

## Claw motor code

1. `garra_v1_drv8825_accelstepper.ino` — first driver (DRV8825),
   AccelStepper library.
2. `garra_v2_l298n_accelstepper.ino` — switched to the L298N driver,
   still on AccelStepper.
3. `garra_v3_pasos_manuales_sin_rampa.ino` — dropped AccelStepper for
   manual coil sequencing, fixed delay (no acceleration ramp yet).
4. `garra_v4_con_boton.ino` — push-button trigger on D22, before
   moving to the always-run-on-power-up version used in the final
   build.

Current version: `garra/garra.ino` — manual step sequencing with an
acceleration ramp, sequence runs once in `setup()`.

## Fossil box code (sensor + HuskyLens + LCD + RTC)

- `caja_fosiles_flags_diagnostico_IR.ino` — a debugging build from
  an earlier session, with `USAR_HUSKYLENS`/`USAR_IR` boolean
  switches added to isolate a failing IR sensor (it was giving
  constant false positives, which triggered HuskyLens nonstop and
  corrupted the LCD through repeated I2C clock switching) without
  unplugging anything. Pin/calibration numbers in this file
  (A2, 996/456) are from that debugging session and don't match the
  current hardware — see the current file for real values.

Current version: `caja/caja_fosiles.ino` — soil sensor on A1
(calibrated 1005/630), IR on D5, HuskyLens classifying four trained
vertebra IDs, RTC-stamped readings sent as CSV over serial to
`web/Servidor_mapa.py`.
