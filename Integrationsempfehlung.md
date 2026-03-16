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

1. **Exyte Control Terminal 3 (CT3)** mit LON/FTT10-IO-Modul verwenden – bietet galvanische Eingänge und ist die herstellereigene Lösung (→ Abschnitt 9)
2. Nur die **drei Kern-NVs** binden: `nviSetSpeed` (Sollwert), `nvoActualSpeed` (Istwert), `nvoFFUState` (Status)
3. **Zykluszeit**: Sollwert bei Änderung senden, Istwert und Status alle 30 s pollen
4. **Fehlerreaktion**: Bei Bits 1, 3, 4 in `nvoFFUState` → Gerät auf 0 RPM setzen und Alarm ausgeben
5. **PID-Vorkonfiguration**: Einmalig bei Inbetriebnahme via LNS-Tool – keine zyklische Änderung notwendig

Diese Minimalintegration ermöglicht eine zuverlässige Drehzahlsteuerung und Fehlerüberwachung mit weniger als 20 Zeilen Steuerungscode.

---

## 9. Galvanisches Ein-/Ausschalten – Exyte Control Terminal 3 (CT3)

Für eine **galvanische Schnittstelle** (Schalter/Relais → vordefinierte Drehzahl) bietet der **Exyte CT3** mit LON/FTT10-IO-Modul oder LON/RS485-IO-Modul die herstellereigene Lösung (Doku: `0958_001.pdf`).

### Technische Spezifikationen IO-Modul

| Merkmal | Wert |
|---|---|
| Digitale Eingänge | 8 × (IN1–IN8, 24VDC) |
| Digitale Ausgänge | 8 × (OUT1–OUT8) |
| Relaisausgang (Basisstation) | 1 × potenzialfrei, max. 24V / 1A |
| Galvanische Trennung | Optisch isolierter Relaisausgang |
| LonWorks-Varianten | LON/FTT10-IO-Modul oder LON/RS485-IO-Modul |
| Max. FFUs pro Kanal | 63 Geräte |

### Funktionsweise – Stufenumschaltung über Digitaleingang

```
Schalter / Relais (24VDC)
        │
        ▼ galvanischer Eingang
  CT3 IO-Modul (IN1 … IN8)
        │
        ▼ konfigurierte Eingang-Aktion
  „Setze Geschwindigkeit auf Drehzahl 2"
        │
        ▼ LonWorks (FTT10 / RS485)
  EC16V700  →  nviSetSpeed = Drehzahl 2 (RPM)
```

**Konfigurierbare Eingang-Aktionen pro Digitaleingang:**
- Keine Aktion
- Setze Geschwindigkeit auf **Drehzahl 2** (vordefinierter RPM-Wert)
- Stoppe Lüftergerät

**Konfigurierbare Ausgang-Aktionen:**
- Ausgang nicht setzen
- Ausgang setzen wenn Drehzahl 2 aktiv
- Ausgang setzen bei Kanalfehler
- Ausgang setzen bei Gesamtfehler

### Konfiguration am CT3

1. Kanal → Gerät auswählen (Geräte-Nr. des EC16V700)
2. Solldrehzahl für **Drehzahl 1** (Normal) und **Drehzahl 2** (Schaltstufe) in % eintragen
3. Eingang-Aktion für IN1–IN8 zuweisen: `„Setze Geschwindigkeit auf Drehzahl 2"`
4. IO-Modul per **Service-Pin-Installation** einbinden (Kanal 10, Gerät 1)

### Verdrahtung IO-Modul (RS485-Variante)

| Kabel-Pin | IO-Modul-Pin | Signal |
|---|---|---|
| 13 | 1 | RS485 A |
| 26 | 2 | RS485 B |

### Verdrahtung IO-Modul (FTT10-Variante)

| Kabel-Pin | IO-Modul-Pin | Signal |
|---|---|---|
| 13 / 26 | 5, 6 | NET A / NET B |
| 1, 3 (Patch) | – | NET A |
| 2, 6 (Patch) | – | NET B |

### Relaisausgang Basisstation (Störmelderelais)

| Pin | Funktion |
|---|---|
| Pin 1 | Öffner (open contact) |
| Pin 2 | Wiper (common) |
| Pin 3 | Schließer (closed contact) |
| Max. Last | 24VDC / 1A |

---

## 10. Moeller Easy 619-DC-RC als vorgelagerte Logik

Der **Moeller Easy 619-DC-RC** (Eaton) kann als programmierbares Steuerrelais eingesetzt werden, um die Digitaleingänge des CT3 IO-Moduls zu schalten – z.B. für zeitgesteuerte Stufenumschaltung oder Verriegelungslogik.

### Technische Spezifikationen

| Merkmal | Wert |
|---|---|
| Versorgung | 24VDC |
| Digitaleingänge | 12 × 24VDC |
| Relaisausgänge | 6 × (max. 250VAC / 8A, potenzialfrei) |
| Echtzeituhr | ja (RC = Real Clock) |
| Kommunikation | easy-NET (proprietär, kein LonWorks) |
| Programmierung | Leiterdiagramm / Funktionsblöcke via easy-SOFT |

### Signalweg Easy 619-DC-RC → CT3 IO-Modul → EC16V700

```
Schalter / BMS-Signal (24VDC)
        │
        ▼
Easy 619-DC-RC
  Logik: z.B. Zeitschaltuhr, Verriegelung, Stufenwahl
  Ausgang Q1 (Relais, potenzialfrei)
        │  24VDC-Schaltspannung
        ▼
CT3 IO-Modul (IN1 … IN8, 24VDC)
  Eingang-Aktion: „Setze Geschwindigkeit auf Drehzahl 2"
        │  LonWorks (FTT10 / RS485)
        ▼
EC16V700  →  nviSetSpeed = Drehzahl 2 (RPM)
```

### Typische Anwendungsfälle

| Funktion | Easy-Konfiguration |
|---|---|
| Zeitgesteuerte Stufenumschaltung | Wochenprogramm (Echtzeituhr) → Q1 schaltet IN1 am CT3 |
| Verriegelung mit Druckwächter | I1 (Druckwächter) AND I2 (Betriebsfreigabe) → Q1 |
| Einschaltverzögerung | I1 EIN → Verzögerungsblock → Q1 (verhindert Kurzzeitpulse) |
| Handbetrieb-Automatik-Umschaltung | I1 = Hand (Q1 direkt), I2 = Auto (Zeitprogramm → Q1) |

### Verdrahtung

| Easy 619 Klemme | CT3 IO-Modul Klemme | Signal |
|---|---|---|
| Q1 (Schließer) | IN1 | 24VDC bei aktivem Ausgang |
| 0V / GND (Easy) | GND (CT3) | gemeinsame Masse |

> **Hinweis:** Da die Relaisausgänge des Easy 619-DC-RC potenzialfrei sind, muss die 24VDC-Versorgung für die CT3-Eingänge extern zugeführt werden (über den Schließerkontakt Q1 schalten).
