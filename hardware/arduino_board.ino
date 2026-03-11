/*
------------------------------------------------------------
Interactive Modular Sensor-Based Game Board
------------------------------------------------------------

Hardware:
- Arduino Mega
- 16 PN532 NFC Readers
- 2x TCA9548A I2C Multiplexers
- Event-driven serial communication

Event format:
UID:XXXXXXXX OldPos action NewPos

Supports scalability up to 64 readers.
------------------------------------------------------------
*/

#include <Wire.h>
#include <Adafruit_PN532.h>

/* ==============================
   Configuration
============================== */

#define NUM_READERS 16
#define MISS_THRESHOLD 12   // Miss count before lift detection

/* ==============================
   Multiplexer Configuration
============================== */

const uint8_t muxAddresses[NUM_READERS] = {
  0x70,0x70,0x70,0x70,0x70,0x70,0x70,0x70,
  0x71,0x71,0x71,0x71,0x71,0x71,0x71,0x71
};

const uint8_t muxChannels[NUM_READERS] = {
  0,1,2,3,4,5,6,7,
  0,1,2,3,4,5,6,7
};

/* ==============================
   Board Positions
============================== */

const char* POSITIONS[NUM_READERS] = {
  "b1","c1","d1","a1",
  "a2","b2","c2","d2",
  "d4","c4","b4","a4",
  "a3","b3","c3","d3"
};

/* ==============================
   Reader Tracking State
============================== */

uint8_t lastUids[NUM_READERS][7];
uint8_t lastUidLengths[NUM_READERS];
uint8_t missCounter[NUM_READERS];

/* ==============================
   Tag Structure
============================== */

struct TagInfo {
  uint8_t uid[7];
  uint8_t uidLen;
  int8_t  currentReader;     // -1 = not on board
  int8_t  lastReader;
  bool    hasEverBeenPlaced;
};

TagInfo tags[] = {
  {{0xC5,0xB7,0xBD,0x01},4,-1,-1,false},
  {{0xF3,0xC7,0xB5,0x01},4,-1,-1,false},
  {{0x9B,0x85,0x08,0x02},4,-1,-1,false},
  {{0x7A,0x74,0xB7,0x01},4,-1,-1,false},
  {{0xAB,0x98,0x08,0x02},4,-1,-1,false},
  {{0x5B,0xCA,0x0E,0x02},4,-1,-1,false},
  {{0x1B,0xFD,0x08,0x02},4,-1,-1,false},
  {{0xCE,0x89,0x0E,0x02},4,-1,-1,false}
};

const uint8_t TAG_COUNT = sizeof(tags) / sizeof(tags[0]);

Adafruit_PN532* readers[NUM_READERS];

/* ==============================
   Helper Functions
============================== */

void tcaSelect(uint8_t readerIndex) {
  Wire.beginTransmission(muxAddresses[readerIndex]);
  Wire.write(1 << muxChannels[readerIndex]);
  Wire.endTransmission();
}

int8_t findTag(uint8_t* uid, uint8_t len) {
  for (uint8_t t = 0; t < TAG_COUNT; t++) {
    if (len == tags[t].uidLen &&
        memcmp(uid, tags[t].uid, len) == 0) {
      return t;
    }
  }
  return -1;
}

void printUid(uint8_t* uid, uint8_t len) {
  for (uint8_t i = 0; i < len; i++) {
    if (uid[i] < 0x10) Serial.print("0");
    Serial.print(uid[i], HEX);
  }
}

void clearUid(uint8_t* uid, uint8_t &len) {
  len = 0;
}

/* ==============================
   Setup
============================== */

void setup() {

  Serial.begin(115200);
  Wire.begin();

  // Initialize tracking arrays
  for (uint8_t i = 0; i < NUM_READERS; i++) {
    lastUidLengths[i] = 0;
    missCounter[i] = 0;
  }

  // Initialize NFC readers
  for (uint8_t i = 0; i < NUM_READERS; i++) {

    tcaSelect(i);
    delay(50);

    readers[i] = new Adafruit_PN532(-1, -1, &Wire);
    readers[i]->begin();
    delay(10);

    if (readers[i]->getFirmwareVersion()) {
      readers[i]->SAMConfig();
      Serial.print("Reader ");
      Serial.print(i);
      Serial.println(" initialized");
    } else {
      Serial.print("No reader at index ");
      Serial.println(i);
    }
  }

  // Initialize tag state
  for (uint8_t t = 0; t < TAG_COUNT; t++) {
    tags[t].currentReader = -1;
    tags[t].lastReader = -1;
    tags[t].hasEverBeenPlaced = false;
  }
}

/* ==============================
   Main Loop
============================== */

void loop() {

  for (uint8_t i = 0; i < NUM_READERS; i++) {

    tcaSelect(i);
    delay(10);

    uint8_t uid[7];
    uint8_t uidLen = 0;

    bool present = readers[i]->readPassiveTargetID(
      PN532_MIFARE_ISO14443A,
      uid,
      &uidLen,
      20
    );

    if (present) {

      missCounter[i] = 0;
      int8_t idx = findTag(uid, uidLen);

      if (idx >= 0) {

        TagInfo &tag = tags[idx];

        // Placement
        if (tag.currentReader < 0) {

          const char* oldPos = tag.hasEverBeenPlaced ?
                               POSITIONS[tag.lastReader] :
                               "00";

          Serial.print("UID:");
          printUid(tag.uid, tag.uidLen);
          Serial.print(" ");
          Serial.print(oldPos);
          Serial.print(" move ");
          Serial.println(POSITIONS[i]);

          tag.hasEverBeenPlaced = true;
        }

        // Slide move
        else if (tag.currentReader != i) {

          Serial.print("UID:");
          printUid(tag.uid, tag.uidLen);
          Serial.print(" ");
          Serial.print(POSITIONS[tag.currentReader]);
          Serial.print(" move ");
          Serial.println(POSITIONS[i]);

          tag.lastReader = tag.currentReader;
        }

        tag.currentReader = i;
        memcpy(lastUids[i], uid, uidLen);
        lastUidLengths[i] = uidLen;
      }
    }

    // Handle Lift
    else {

      if (lastUidLengths[i] > 0) {

        missCounter[i]++;

        if (missCounter[i] >= MISS_THRESHOLD) {

          int8_t idx = findTag(lastUids[i], lastUidLengths[i]);

          if (idx >= 0) {

            TagInfo &tag = tags[idx];

            if (tag.currentReader == i) {

              Serial.print("UID:");
              printUid(tag.uid, tag.uidLen);
              Serial.print(" ");
              Serial.print(POSITIONS[i]);
              Serial.println(" lift 00");

              tag.lastReader = tag.currentReader;
              tag.currentReader = -1;
            }
          }

          clearUid(lastUids[i], lastUidLengths[i]);
          missCounter[i] = 0;
        }
      }
    }

    delay(10);
  }
}
