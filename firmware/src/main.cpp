// USB-serial → Xbox Series X BLE controller bridge. Frame format: see README.md, "Serial protocol".
#include <Arduino.h>
#include <BleGamepad.h>

#define SYNC 0xA5
#define FRAME_LEN 15
#define MIN_SEND_MS 7    // don't queue faster than BLE can deliver
#define WATCHDOG_MS 200  // no frame for this long -> neutral
#define SHARE_BIT 11     // bits 0..10 = library buttons 1..11, bit 11 = Share

BleGamepad bleGamepad;
BleGamepadConfiguration config;

uint8_t buf[FRAME_LEN];
uint8_t len = 0;
uint8_t state[FRAME_LEN - 2]; // last applied payload (bytes 1..13)
bool dirty = false;
unsigned long lastFrame = 0, lastSend = 0;

static int16_t rd16(const uint8_t *p) { return (int16_t)(p[0] | (p[1] << 8)); }

void apply(const uint8_t *p) // p = bytes 1..13
{
  if (memcmp(p, state, sizeof(state)) == 0)
    return;
  memcpy(state, p, sizeof(state));
  uint16_t btn = p[0] | (p[1] << 8);
  bleGamepad.setButtonsFromMask(btn & 0x7FF);
  if (btn & (1 << SHARE_BIT))
    bleGamepad.pressSpecialButton(BACK_BUTTON);
  else
    bleGamepad.releaseSpecialButton(BACK_BUTTON);
  bleGamepad.setHat1(p[2]);
  bleGamepad.setLeftThumb(rd16(p + 3), rd16(p + 5));
  bleGamepad.setRightThumb(rd16(p + 7), rd16(p + 9));
  bleGamepad.setLeftTrigger(p[11] * 32767 / 255);
  bleGamepad.setRightTrigger(p[12] * 32767 / 255);
  dirty = true;
}

void setup()
{
  Serial.begin(115200);
  config.setGamepadMode(GamepadMode::XInputSeriesX);
  config.setAutoReport(false);
  bleGamepad.begin(&config);
  memset(state, 0xFF, sizeof(state)); // force first apply
  uint8_t neutral[FRAME_LEN - 2] = {};
  apply(neutral);
}

void loop()
{
  while (Serial.available())
  {
    uint8_t b = Serial.read();
    if (len == 0 && b != SYNC)
      continue; // resync
    buf[len++] = b;
    if (len < FRAME_LEN)
      continue;
    uint8_t x = 0;
    for (int i = 1; i < FRAME_LEN - 1; i++)
      x ^= buf[i];
    if (x == buf[FRAME_LEN - 1])
    {
      apply(buf + 1);
      lastFrame = millis();
      len = 0;
    }
    else
    {
      // bad frame: restart from the next sync byte inside it
      int i = 1;
      while (i < FRAME_LEN && buf[i] != SYNC)
        i++;
      len = FRAME_LEN - i;
      memmove(buf, buf + i, len);
    }
  }

  unsigned long now = millis();
  if (now - lastFrame > WATCHDOG_MS)
  {
    uint8_t neutral[FRAME_LEN - 2] = {};
    apply(neutral);
  }
  if (dirty && now - lastSend >= MIN_SEND_MS && bleGamepad.isConnected())
  {
    bleGamepad.sendReport();
    lastSend = now;
    dirty = false;
  }
}
