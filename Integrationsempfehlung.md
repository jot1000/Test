# Integrationsempfehlung: EC16V700 in eine einfache Steuerung

**Gerät:** EC-LON-FFU Closed-Loop-Aktuator (Modell EC16V700)
**Protokoll:** LonWorks / LonTalk (Neuron-Mikrocontroller, LONNCC32 V4.03.09)
**Einsatzzweck:** Netzwerkgesteuertes Ventilatoraggregat mit geschlossenem Regelkreis

---

## 1. Zusammenfassung des Geräts

Das EC16V700 ist ein LonMark-kompatibles Feldgerät zur präzisen Drehzahlregelung von Ventilatoren (FFU – Fan Filter Units). Es kommuniziert über **LonTalk** via Netzwerkvariablen (NVs) und bietet:

- Sollwert-Eingabe: **300–2050 RPM** (oder 0 = Stop)
- Istwert-Rückmeldung (Regelabweichung < ±5%)
- Integrierter **PID-Regler** (konfigurierbar)
- **Fehlerprotokoll** (letzte 4 Ereignisse mit Zeitstempel)
- Betriebsstundenzähler (persistent im EEPROM)

---

## 2. Relevante Netzwerkvariablen für die Steuerung

### Pflicht-Variablen (Minimalintegration)

| Variable        | Richtung | Typ  | Beschreibung                          |
|-----------------|----------|------|---------------------------------------|
| `nviSetSpeed`   | Eingang  | WORD | Drehzahlsollwert in RPM (0 = Stop)    |
| `nvoActualSpeed`| Ausgang  | WORD | Aktueller Istwert in RPM              |
| `nvoFFUState`   | Ausgang  | WORD | 9-Bit-Statusregister (Fehlerflags)    |

### Erweiterte Variablen (empfohlen)

| Variable          | Richtung | Typ     | Beschreibung                              |
|-------------------|----------|---------|-------------------------------------------|
| `nvoSetSpeedFb`   | Ausgang  | WORD    | Bestätigung des empfangenen Sollwerts     |
| `nviPID`          | Eingang  | 5×BYTE  | PID-Koeffizienten (Kp, Ki, Kd) + Offset  |
| `nviRPM`          | Eingang  | 4×WORD  | RPM-Parameter (ASmax, Pup, RSmax, RSmin)  |
| `nvoGetRunTime`   | Ausgang  | Struct  | Betriebsstunden (Diagnose)               |
| `nvoErrLog`       | Ausgang  | 28 Byte | Fehlerprotokoll (4 × Ereignis+Zeitstempel)|
| `nviTimeSync`     | Eingang  | Struct  | Zeitsynchronisation vom Master           |

---

## 3. Statusregister `nvoFFUState` – Bitbelegung

| Bit | Bedeutung          | Aktion in der Steuerung              |
|-----|--------------------|---------------------------------------|
| 0   | Kommunikationsfehler | Alarmierung, Neuverbindung versuchen |
| 1   | Motor blockiert    | NOT-STOP, Wartung anfordern           |
| 3   | Lager-/Lüfterfehler| Gerät sperren, Wartung anfordern     |
| 4   | Temperaturüberschreitung | Sollwert reduzieren / abschalten |
| 7   | Zeitsync-Status    | Info (kein Fehler)                   |
| 8   | Wink-Indikator     | Info / Diagnose                      |

---

## 4. Empfohlene Integrationsarchitektur

```
┌─────────────────────────────┐       LonWorks TP/FT-10
│      Übergeordnete           │       (78 kBit/s Freifeld-Bus)
│      Steuerung / BMS         │◄─────────────────────────────►┌──────────────────┐
│  (z.B. SPS, DDC-Controller)  │                               │   EC16V700       │
│                              │   nviSetSpeed ─────────────►  │  (FFU-Aktuator)  │
│   Sollwert ausgeben          │   nvoActualSpeed ◄──────────  │                  │
│   Istwert einlesen           │   nvoFFUState ◄─────────────  │  PID-Regler      │
│   Fehler auswerten           │                               │  geschlossen     │
└─────────────────────────────┘                               └──────────────────┘
         │
         │ Optional: LNS-Server / IP-852 Router
         │ für Remote-Monitoring & Konfiguration
```

### Voraussetzungen für den LonWorks-Anschluss

- **LonWorks-Transceiver** am Controller: TP/FT-10 (78 kBit/s, verdrillte Zweidrahtleitung)
- **Netzwerkmanagement**: Echelon LNS oder OpenLDV / OpenLNS Toolkit
- Alternativ: **IP-852 Channel Router** für LonWorks-over-IP

---

## 5. Schritte zur Inbetriebnahme

1. **Netzwerkvariablen binden** (`nviSetSpeed` → Controller-Ausgang, `nvoActualSpeed` / `nvoFFUState` → Controller-Eingänge) via LNS-Netzwerkmanager oder manuell per Explicit Messaging.

2. **Selbstkonfiguration auslösen** (einmalig):
   `nviSelfConfig` auf Subnet/Node = `1/1` setzen → Gerät speichert Konfiguration ins EEPROM.

3. **PID-Regler parametrieren** (optional, Werkseinstellung prüfen):
   `nviPID` mit Kp, Ki, Kd, Speed-Offset, DCI-Relais-Steuerung beschreiben.

4. **Drehzahlbereich einschränken** (optional):
   `nviRPM` mit ASmax, Pup, RSmax, RSmin gemäß Anlagenauslegung setzen.

5. **Zeitsynchronisation** einrichten:
   `nviTimeSync` zyklisch (z.B. täglich) vom Zeitmaster beschreiben.

6. **Fehlermonitoring** integrieren:
   `nvoFFUState` zyklisch pollen (empfohlen: alle 10–60 s).
   Bei gesetzten Fehlerbits → Alarm im BMS/GLT auslösen und `nvoErrLog` auslesen.

---

## 6. Einfachste Minimalsteuerung (ohne LNS)

Für eine sehr einfache Steuerung ohne volles LNS-Netzwerkmanagement:

```
Steuerung sendet: Explicit Message an Neuron-Adresse
  → NV-Index 2 (nviSetSpeed): 2 Byte, gewünschte RPM als WORD (Big Endian)

Steuerung liest: Poll-Requests
  ← NV-Index 4 (nvoActualSpeed): aktueller RPM-Istwert
  ← NV-Index 5 (nvoFFUState):    Statusregister
```

**Voraussetzung:** Subnet/Node-Adresse des Geräts ist bekannt (Default: konfigurierbar via `nviSelfConfig`).

---

## 7. Besonderheiten und Hinweise

| Thema | Hinweis |
|-------|---------|
| **EEPROM-Schreibzyklen** | `nviRPM`, `nviPID`, `nviTypeInfo` sind EEPROM-Variablen → max. ~100.000 Schreibzyklen; nicht zyklisch beschreiben |
| **Betriebsstunden** | `nvoGetRunTime` wird nur alle 2 Tage und beim Abschalten aktualisiert |
| **Drehzahlbereich** | Minimalwert: 300 RPM; unterhalb stoppt das Gerät sicher |
| **HT-Messaging** | Fehleralarm-Routing über `nciMSGH` (Subnet/Node des Alarm-Empfängers) konfigurierbar |
| **Firmware-Update** | `.NEI`/`.NXE` Dateien via Echelon NodeLoad-Tool laden |

---

## 8. Fazit und Empfehlung

**Für eine einfache Steuerungsintegration** wird empfohlen:

1. **LonWorks TP/FT-10 Schnittstelle** am Controller verwenden (z.B. PCI-Karte oder USB-Adapter mit OpenLDV)
2. Nur die **drei Kern-NVs** binden: `nviSetSpeed` (Sollwert), `nvoActualSpeed` (Istwert), `nvoFFUState` (Status)
3. **Zykluszeit**: Sollwert bei Änderung senden, Istwert und Status alle 30 s pollen
4. **Fehlerreaktion**: Bei Bits 1, 3, 4 in `nvoFFUState` → Gerät auf 0 RPM setzen und Alarm ausgeben
5. **PID-Vorkonfiguration**: Einmalig bei Inbetriebnahme via LNS-Tool – keine zyklische Änderung notwendig

Diese Minimalintegration ermöglicht eine zuverlässige Drehzahlsteuerung und Fehlerüberwachung mit weniger als 20 Zeilen Steuerungscode.
