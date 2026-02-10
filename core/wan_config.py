"""
Zentrale WAN-Parameter (ohne GUI).

Hier kannst du die Berechnungslogik global steuern.
Änderung = Datei speichern = Server neu starten.
"""

# Benötigte Mbit/s pro Arbeitsplatz (Down / Up)
WAN_MBIT_PER_AP_DOWN = 10
WAN_MBIT_PER_AP_UP = 2

# Ampel-Schwellen (Ist/BEDARF)
# grün: >= 130% Bedarf
WAN_THRESHOLD_GREEN = 1.30

# gelb: >= 90% Bedarf
WAN_THRESHOLD_YELLOW = 0.90
