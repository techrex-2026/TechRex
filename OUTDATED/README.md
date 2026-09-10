# Retired code

Progression of the claw motor code, kept for reference. Each file's
header explains what it tried and why it was replaced.

1. `garra_v1_drv8825_accelstepper.ino` — first driver (DRV8825),
   AccelStepper library.
2. `garra_v2_l298n_accelstepper.ino` — switched to the L298N driver,
   still on AccelStepper.
3. `garra_v3_pasos_manuales_sin_rampa.ino` — dropped AccelStepper for
   manual coil sequencing, fixed delay (no acceleration ramp yet).
4. `garra_v4_con_boton.ino` — push-button trigger on D22, before
   moving to the always-run-on-power-up version used in the final
   build.

The current version is `garra/garra.ino` — manual step sequencing
with an acceleration ramp, sequence runs once in `setup()`.
