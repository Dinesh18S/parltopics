from parltopics.sources.langcheck import detect_lang


def test_detects_de_fr_it():
    assert detect_lang("Der Bundesrat wird beauftragt, die gesetzlichen Grundlagen für den Schutz der Daten zu schaffen und dies auch zu prüfen.") == "de"
    assert detect_lang("Le Conseil fédéral est chargé de créer les bases légales pour la protection des données et de les mettre en œuvre dans les cantons.") == "fr"
    assert detect_lang("Il Consiglio federale è incaricato di creare le basi legali per la protezione dei dati e di sottoporre una proposta alla Commissione.") == "it"


def test_too_short_returns_none():
    assert detect_lang("Digitalisierung") is None
    assert detect_lang("") is None
