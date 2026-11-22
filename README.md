# Hack Apertus Liebefeld — OpenParlData: Themenklassifikation für Schweizer Parlamente mit Apertus — Unisono

**Team Unisono:** Selvadinesh Sasikumar (Entwicklung, Deployment) · Arivinchsa Thilagarajah (Recherche, Datensatz, Pitch)

Schweizer Parlamente veröffentlichen über OpenParlData.ch Hunderttausende von Geschäften (Motionen, Interpellationen,
Vorlagen), doch ihre Themen-Labels sind grob und von Parlament zu Parlament uneinheitlich. Monitoring-Dienste wie
PolitMonitor verschlagworten Geschäfte von Hand, und eine Stichwortsuche übersieht Geschäfte, in denen das Wort nie
vorkommt. Die Challenge: Mit Apertus sollen Geschäfte aus Bundes-, Kantons- und Gemeindeparlamenten nach Thema
klassifiziert werden — auf Deutsch, Französisch und Italienisch —, sowohl in ein Standardschema als auch in Ad-hoc-Themen
wie «Digitalisierung», und das Ergebnis soll an den manuellen Tags gemessen werden.

Einreichungen müssen die Modellfamilie Apertus v1.5 verwenden.
Die Einreichung muss den [HackApertus-AGB](https://hackapertus.ch/terms-and-conditions) entsprechen.

## 🎯 Die Challenge

**OpenParlData: Themenklassifikation für Schweizer Parlamente mit Apertus** —
[hackapertus.notion.site/openparldata](https://hackapertus.notion.site/openparldata)

## Unisono — offener Themenklassifikator für Schweizer Parlamentsgeschäfte

Unisono findet jedes Geschäft zu einem Thema, auf Deutsch, Französisch und Italienisch, und zeigt den Satz, der es belegt.

**Demo-Video (2 Min.):** [youtu.be/EpF6-megCrY](https://youtu.be/EpF6-megCrY) · **Technischer Bericht:** [`technical_report.md`](technical_report.md)

- **Ad-hoc-Modus:** einen beliebigen Themennamen plus eine einzeilige Definition eingeben («Digitalisierung», «Wolf») —
  ohne Neutraining.
- **Standardmodus:** Année Politique Suisse (Kapitel → Thema) oder Sachbereiche von Curia Vista.
- **Belege, geprüft durch Code:** Apertus v1.5 70B antwortet mit einem Label, einer Konfidenz und einem Satz, der aus
  dem Geschäft kopiert ist. Reiner Python-Code prüft, ob der Satz tatsächlich in der Quelle steht; ohne verifizierten
  Beleg wird nichts angezeigt. Ein Mensch bestätigt oder verwirft jeden Vorschlag; bestätigte Geschäfte lassen sich
  nach Excel exportieren.
- **Ganze Parlamente:** Bund (27'465 Geschäfte), Bern (5'249) und Thurgau (1'447) seit 2018 sind indexiert;
  `update` klassifiziert nur neue Geschäfte («Was ist neu»).
- **Souverän:** ein OpenAI-kompatibler Endpunkt, der Apertus bereitstellt (lokal mit vLLM/Ollama oder in der Schweiz
  gehostet); läuft auch ohne Internetverbindung mit Docker + SQLite. Ohne Endpunkt startet die App im Cache-Modus mit
  vorberechneten Ergebnissen.

**Ergebnisse (Digitalisierung, alle Geschäfte seit 2018, verglichen mit den manuellen Tags von PolitMonitor):**

| Parlament | Unisono Precision / Recall | Stichwortsuche | Curia-Vista-Sachbereich |
|---|---|---|---|
| Bund | **62.9 % / 51.0 %** | 41.3 % / 56.4 % | 40.9 % / 80.2 % |
| Bern | **68.2 % / 67.8 %** | 32.7 % / 47.4 % | — |
| Thurgau | **50.0 % / 45.5 %** | 15.7 % / 72.7 % | — |

Es wurden 269 getaggte Geschäfte gefunden, die keines der Kernstichwörter enthalten; dasselbe Geschäft erhält in
DE/FR/IT in 94 % der Fälle dieselbe Antwort. Methode, Einschränkungen und alle Zahlen:
[`technical_report.md`](technical_report.md), [`results/metrics.md`](results/metrics.md).

**So funktioniert es:** OpenParlData-API / Bulk-Dateien → Text zusammenstellen (Titel, eingereichter Text, Begründung,
Antwort, Dokumente; bereinigt, auf 12'000 Zeichen gekürzt) → Apertus (striktes JSON) → Beleg prüfen (reiner Code) →
SQLite (nur anhängend) → Web-UI mit menschlicher Prüfung. Entwickler-Dokumentation: [`docs/`](docs/); KI-Coding-Agenten
beginnen bei [`AGENTS.md`](AGENTS.md).

**Vorlage und KI-Werkzeuge:** Ausgangspunkt war das Vorlage-Repository von Hack Apertus Liebefeld. Claude (Anthropic)
wurde während der Entwicklung als KI-Coding-Assistent eingesetzt (Code, Tests, Dokumentation, unter Anleitung des Teams);
es ist nicht Teil der Pipeline — sämtliche Klassifikation und Übersetzung laufen über Apertus.

**Daten:** Quelle: OpenParlData.ch — lizenziert unter CC BY 4.0. Challenge-Dateien: files.openparldata.ch/hackapertus.
Referenz-Labels: Digitalisierungs-Tags von PolitMonitor (Challenge-Dateien). Themenschemata: Curia Vista, Année
Politique Suisse. `data/` enthält nur eingefrorene Stichproben-IDs, die Themendefinition und Prüfblätter; die Rohdateien
werden mit `make data` heruntergeladen.

## 🔧 Ressourcen & Werkzeuge

Ausführliche Informationen findest du auf unserer Seite zu Ressourcen & Werkzeugen:
[https://hackapertus.notion.site/liebefeld-resources-tools](https://hackapertus.notion.site/liebefeld-resources-tools)

| Modelle          | URL                                      |
|------------------|------------------------------------------|
| Apertus v1.5 8B  | [huggingface.co/swiss-ai/Apertus-v1.5-8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B)  |
| Apertus v1.5 70B | [huggingface.co/swiss-ai/Apertus-v1.5-70B](https://huggingface.co/swiss-ai/Apertus-v1.5-70B) |

## Die Struktur

Behalte die Dateien und Verzeichnisse wie unten gezeigt bei — nicht umbenennen oder verschieben.

| Pfad | Was es ist |
| --- | --- |
| `README.md` | Die Challenge-Beschreibung und die Einreichungsanforderungen |
| `technical_report.md` | Die ausführliche Beschreibung: Architektur, Evaluation, Einschränkungen |
| `LICENSE` | Apache-2.0 |
| `src/` | Dein Code |

## Umgebung

- Füge die Anleitung zum Ausführen des Projekts in deinen technischen Bericht ein.
- Verwende die folgenden Umgebungsvariablen:
```
LLM_NAME — Name und Version des Modells
LLM_BASE_URL — Basis-URL des Endpunkts
LLM_API_KEY — dein API-Schlüssel
```

### Unisono ausführen

Voraussetzungen: Docker (oder [uv](https://docs.astral.sh/uv/) für `make dev`) und ein OpenAI-kompatibler Endpunkt,
der Apertus bereitstellt. Ohne Endpunkt startet die App trotzdem, im Cache-Modus.

```bash
cp .env.example .env   # LLM_NAME, LLM_BASE_URL, LLM_API_KEY setzen
make run               # Docker; App auf http://localhost:8080, /health prüfen
make dev               # dasselbe ohne Docker (benötigt uv)
make data              # Challenge-Dateien nach data/raw herunterladen und Prüfsummen kontrollieren
make test              # Unit-Tests
make status            # Stand der Dinge: Slices, Erfolgskriterien, Einreichungs-Checkliste
make first-loop        # 20 Positive + 20 Negative → Tabelle, Genauigkeit, Anteil verifizierter Belege
uv run parltopics data load-bulk            # einmalig: Bundes-Bulk-Texte → data/cache/bulk.db (nötig für > ~500 Geschäfte)
uv run parltopics runs                      # gespeicherte Läufe (SQLite: data/parltopics.db)
uv run parltopics partner files             # Excel-Dateien für den Fachpartner → data/gold/for_partner/
make eval RUN="<dev_run> <test_run>"        # Digitalisierungs-Evaluation (gleiche Bedingungen) → results/metrics.json + metrics.md
uv run parltopics demo export               # results/demo/*.json aktualisieren (zwischengespeicherte Demo-Ergebnisse für den Offline-Modus)
uv run parltopics demo export-collections   # results/collections/*.json.gz aktualisieren (Offline-Kopien ganzer Parlamente)
uv run parltopics review add <prediction_id> confirm|reject|correct [--label …]   # menschliche Prüfung, nur anhängend
uv run parltopics ingest --body BE --since 2018-01-01    # ganzes Parlament: jedes Geschäft einmal abrufen + zusammenstellen, Datenqualitätsbericht
uv run parltopics index --body BE --topic topics/digitalisation.yaml   # alles klassifizieren (oder --scheme aps); fortsetzbar
uv run parltopics update --body BE           # nur Geschäfte seit dem letzten Ingest → klassifizieren → «Neu»-Feed (Cron)
uv run parltopics export --body BE --topic topics/digitalisation.yaml  # Excel/CSV mit Prüfstatus → data/exports/
uv run parltopics fetch 235308 --lang fr   # Text, den das Modell sieht (--lang nur für Bundesgeschäfte)
uv run parltopics classify --affair 235308 --lang de --topic topics/digitalisation.yaml   # ein Modellaufruf
```

## 📦 Einreichungsanforderungen & Ergebnisse

Die Einreichung muss:
1. der Vorlage-Repo folgen und alle erforderlichen Dateien und Definitionen enthalten
2. durchgängig laufen, wenn die Jury sie ausprobiert

### Git-Repo (URL)
- Erstelle dein Repo aus dieser Vorlage (**Use this template**).
- Behalte die Struktur bei: Dateien nicht umbenennen oder verschieben.
- Setze das Repo auf ÖFFENTLICH (Settings --> Collaborators --> Manage Visibility)
- Reiche die URL DEINES Git-Repos ein.

### Technischer Bericht (PDF)
- Aktualisiere [technical_report.md](technical_report.md) in diesem Repository mit allen Details zu deiner Einreichung.
- Lade ein PDF deines technischen Berichts ins Hauptverzeichnis des Repos hoch, benannt als `TeamName_Report.pdf`.
- Format: PDF, max. 6 Seiten ohne Literaturverzeichnis
- Reiche das PDF des technischen Berichts ein.

### Demo-Video (URL)
- Max. 2 Min. langes Demo-Video deines Prototyps
- Füge den Link im Feld **Demo** oben in [technical_report.md](technical_report.md) ein
- Reiche die URL des Videos ein.

## ⚖️ Bewertungskriterien

Jede Challenge hat ihre eigenen Kriterien, die in ihrer Challenge-Beschreibung aufgeführt sind.

Die Hauptjury bewertet jede Einreichung in 6 Dimensionen (relevant für die Top-6-Teams):
1. **Zielgerichteter Einsatz von KI**
2. **Technische Sorgfalt**
3. **Nutzen, Kosten & Skalierbarkeit**
4. **Souveräne Einsetzbarkeit**
5. **Umsetzbarkeit**
6. **Pitch & Präsentation**

Jede Dimension wird mit 0 bis 5 Punkten bewertet.

## Erste Schritte

1. Klicke auf **Use this template**, um dein eigenes Repository zu erstellen.

## Lizenz

Alle Hack-Apertus-Projekte sind Open Source. Die genauen Lizenzbestimmungen findest du in unseren AGB (6. Was du baust, ist Open Source): https://hackapertus.ch/terms-and-conditions

## Support

### FAQ
💡 https://hackapertus.ch/faq

### Kontakt

💬 Bei Fragen tritt der Diskussion auf Discord bei. Alternativ kannst du eine E-Mail an «hello@hackapertus.ch» senden.
