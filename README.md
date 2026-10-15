# GRABUNGSTAUGLICH

Grabungsfotos umbenennen, einsortieren und katalogisieren. Aus Rohfotos, die nur
grob nach Stelle und Position benannt sind, entstehen Dateinamen im WNK-Format,
ein einheitlicher Abgabeordner und die passende Fotoliste als CSV.

Das Programm läuft offline mit Python 3 und Tkinter, ohne zusätzliche Pakete.

## Start

```bash
python GRABUNGSTAUGLICH.py
```

Unter Windows genügt ein Doppelklick auf `start.bat`.

## Vorbereitung der Fotos

Die Rohfotos müssen lediglich nach Stelle und Position benannt sein. Als Trenner
sind Leerzeichen, Bindestriche und Unterstriche erlaubt, auch mehrere
hintereinander.

| Rohfoto | Ergebnis |
|---|---|
| `4-5.jpg` | `AKTIVITÄT_0004_005.jpg` |
| `120_2.jpg` | `AKTIVITÄT_0120_002.jpg` |
| `3     15.jpg` | `AKTIVITÄT_0003_015.jpg` |
| `6------3.jpg` | `AKTIVITÄT_0006_003.jpg` |

Die Stellennummer wird auf vier Stellen aufgefüllt, die Position auf drei.
Kameranamen wie `IMG_0412.jpg` bleiben unangetastet. Verarbeitet werden
JPG-Dateien.

## Funktionen

- **Umbenennen, Abgabeordner und Fotoliste erstellen** in einem Durchgang. Alle
  fertigen Bilder landen im Ordner `Aktivität_Fotos`.
- **Nur umbenennen**, ohne zu verschieben.
- **Bereits umbenannte Fotos aufspüren**, verschieben und katalogisieren.
- **Nur Fotoliste erstellen**, ohne Dateien anzufassen.
- **Bestehende Digitalbildliste aktualisieren**. Vorhandene Kommentare bleiben
  erhalten, es werden nur fehlende Einträge ergänzt.
- **Rückgängig machen**. Jeder Klick nimmt die letzte Aktion zurück:
  Dateibewegungen werden zurückgenommen, Listen erhalten den Stand unmittelbar
  vor dieser Aktion. Wurde eine Liste danach noch von Hand geändert, wird
  dieser Stand vorher als `.vor-undo` gesichert. Überschrieben wird dabei
  nichts: Liegt unter einem alten Fotonamen inzwischen ein anderes Foto,
  kommt das zurückgeholte als `… (UNDO).jpg` daneben.

## Keine doppelten Einträge

Jede Kombination aus Aktivität, Stelle und Position steht höchstens einmal in
der Fotoliste, auch wenn derselbe Ordner mehrfach bearbeitet wird. Mehrere
Fotos derselben Stelle und Position (etwa `…_0005_010.jpg` und
`…_0005_010_A.jpg`, oder ein liegengebliebenes Rohfoto neben der umbenannten
Kopie) ergeben einen einzigen Eintrag. Doppelte Einträge, die schon in einer
vorhandenen Liste stehen, führt das Programm auf Wunsch verlustfrei zusammen.
Widersprechen sich ihre Angaben, bleiben beide Zeilen stehen und werden zum
Prüfen genannt. Unterordner im fertigen Fotoordner, etwa `…_Fotos/aussortiert`,
werden weder verschoben noch gelistet.

Vorhandene Listen werden vollständig gelesen, auch wenn sie in Excel als
UTF-8 gespeichert wurden, eine Zeile `sep=;` oder einen Titel über der
Kopfzeile haben oder Zeilen ohne Stellennummer enthalten. Eigene
Zusatzspalten, Notiz- und Trennzeilen bleiben erhalten und an ihrem Platz.
Gesucht wird die Liste im Ordner der Maßnahme, in Nachbarordnern derselben
Maßnahme (etwa `…_Abgabe`) und daneben. SfM-, Fund- und andere Listen werden
nie als Fotoliste genommen, Kopien nur, wenn es keine bessere gibt.

## Speichern

Bevor eine Fotoliste geschrieben wird, erscheint immer ein Speichern-Dialog. Er
zeigt die Zieldatei, die Zahl der neuen Einträge und gefundene Dopplungen. Über
»Speicherort ändern…« lässt sich die Liste woanders speichern. Ist das Ziel eine
vorhandene Fotoliste, wird sie ergänzt, nicht ersetzt. Vor jedem Überschreiben
entsteht eine Sicherung (`.bak`).

## Einzel- und Batchmodus

Im Einzelmodus wird ein Quellordner gewählt, die Aktivität ergänzt das Programm
aus dem Ordnernamen oder den Nachbarordnern. Im Batchmodus genügt ein
übergeordneter Ordner: Alle Maßnahmen darin werden erkannt und nacheinander
abgearbeitet, jede mit eigenen Fotografennamen. Gehören mehrere Ordner zu
einer Maßnahme, zeigt der Block sie einzeln zum Abwählen an. Eindeutige Kopien
(`… - Kopie`, `(2)`, `Backup` oder ein anderer Ordner der Maßnahme mit
angehängtem `_alt`) sind vorab abgewählt; Ortsnamen wie `Morschenich-Alt`
gelten nicht als Kopie. Gespeichert wird
im Batchmodus erst nach einem gemeinsamen Dialog, in dem jede Liste einzeln
abgehakt wird. Würden zwei Maßnahmen in dieselbe Datei schreiben, verhindert
das Programm das Speichern, bis der Konflikt gelöst ist.

## Fotografinnen und Fotografen

Ein Hauptname gilt für alle Fotos. Abweichungen lassen sich gezielt eintragen,
indem zum Namen die betroffenen Aufnahmen als Stelle und Position angegeben
werden, etwa `3-14, 6-20`. Diese Angabe hat Vorrang vor dem Hauptnamen.

## Aufnahmedatum

Das Datum stammt aus den EXIF-Daten. Liegt es vor dem Jahr der Aktivität, blockt
das Programm normalerweise ab, weil meist die Kamerauhr zurückgesetzt wurde. Auf
Wunsch lässt sich diese Sperre aufheben: Die Fotos werden dann umbenannt und das
Datum in der Liste bleibt leer.

## Hinweise

Eine ausführliche Anleitung steckt im Programm selbst und ist über den
Hilfe-Knopf erreichbar. Die erzeugten Listen und die Fotos gehören nicht ins
Repository, die `.gitignore` hält sie draußen.

## Lizenz

GNU General Public License Version 3, siehe [LICENSE](LICENSE).

Keine Gewährleistung. Die Nutzung erfolgt auf eigene Verantwortung, der Autor
übernimmt keine Haftung für Schäden, Datenverluste oder Fehlinterpretationen der
Ergebnisse. Vor größeren Läufen eine Sicherungskopie anlegen.

© 2026 Peter Meurer
