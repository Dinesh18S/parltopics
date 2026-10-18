# First loop (S4) — 2026-10-18

Sample: data/samples/first_loop.csv (20 PolitMonitor positives + 20 in-scope negatives, seed 42, all dev). Model apertus-v1-5-70b.

## Partner definition (prompt_version 3e7c090902c6) vs old draft (f5aca487d27c)

```
id      body  lang gold label     conf status          ev     kw_abs t_only ms     title                                           
201152  AR    de   1    match     0.90 ok              exact                5704   Geschäftsbericht und Jahresrechnung 2023 der AR 
64439   CHE   it   1    no_match  0.00 ok                     yes           3143   Escludere le PMI dalla tassa sui media          
66904   CHE   fr   1    no_match  0.00 ok                                   4619   Travail à domicile. Créer les bases légales néce
156184  CHE   it   1    no_match  0.60 ok                                   3545   Garantire la partecipazione e la diversità cultu
160043  CHE   de   1    match     1.00 ok              exact                4085   Vollständigkeit des Transparenzregisters für den
234879  CHE   fr   1    match     0.85 ok              exact                2621   Recherche automatisée de véhicules et surveillan
236019  CHE   de   1    match     1.00 ok              exact                4099   Digitale Souveränität der Schweiz ist Realität! 
246392  JU    fr   1    match     0.60 ok              exact         yes    1611   Dossier électronique du patient                 
216800  NE    fr   1    no_match  0.00 ok                                   6236   Inventaire électronique des installations d’appr
77719   OW    de   1    match     1.00 ok              exact                5818   Digitalstrategie 2025 bis 2028                  
182664  OW    de   1    match     1.00 ok              exact                3835   Nachtrag zum Datenschutzgesetz                  
83928   TI    it   1    match     1.00 ok              exact                4598   Come facciamo con l'APP Chat GPT a scuola       
85111   TI    it   1    match     0.90 ok              exact                4948   Adeguamento e armonizzazione delle basi legali n
173404  TI    it   1    match     1.00 ok              exact                3984   Consultazione sulla «Strategia per la trasformaz
329562  TI    it   1    match     1.00 ok              fuzzy                5096   Per un’intelligenza artificiale pubblica svizzer
199901  UR    de   1    no_match  0.00 ok                                   3877   «Offenheit und Transparenz in Uri»              
226793  VD    fr   1    match     0.85 ok              exact                5057   Registre des automobilistes et sécurité des donn
227082  VD    fr   1    match     1.00 ok              exact                4601   Data Center de St-Triphon : des mesures contre l
229042  VD    fr   1    no_match  0.00 ok                                   2793   EMPD autorisant l'accès de la Policlinique médic
91330   ZH    de   1    match     0.90 ok              exact                2744   Abraxas, Justizsoftware, Schlüssel und Microsoft
201014  AR    de   0    no_match  0.00 ok                     yes           2455   Fragestunde vom 23. September 2024              
155916  CHE   fr   0    no_match  0.00 ok                                   4613   Contre la distribution des bénéfices des entrepr
160235  CHE   fr   0    no_match  0.00 ok                     yes           4058   Pour le maintien en service des centrales nucléa
202428  CHE   it   0    no_match  0.00 ok                                   2460   Come rafforzare la fiducia degli agricoltori nei
213852  CHE   de   0    no_match  0.00 ok                     yes           3390   Keine ausreichenden Mittel für die Bekämpfung de
216006  CHE   it   0    no_match  0.00 ok                     yes           2645   Il DFGP deve potenziare senza indugio la Polizia
234707  CHE   de   0    abstain   0.30 ok                     yes    yes    2753   Dienstpflicht der Zukunft                       
286923  JU    fr   0    no_match  0.00 ok                                   6434   Réorganisation du Service juridique et du Servic
216730  NE    fr   0    no_match  0.00 ok                     yes           3226   Politique de subventionnement, l’État est-il dev
167678  OW    de   0    no_match  0.00 ok                     yes    yes    2221   Entschädigungspflicht von Nutztieren, die durch 
336119  OW    de   0    match     0.70 evidence_failed not_fo               3266   Bericht der Interparlamentarischen Fachhochschul
83793   TI    it   0    no_match  0.00 ok                                   2888   Nuovi finanziamenti per CASI DI RIGORE-COVID 19 
83985   TI    it   0    no_match  0.00 ok                     yes           5326   Donne maltrattate e strutture di accoglienza: a 
173899  TI    it   0    no_match  0.00 ok                     yes           4629   Chiarezza su alcune dinamiche che coinvolgono Sp
175950  TI    it   0    no_match  0.00 ok                     yes           2633   Per una presa a carico razionale delle problemat
200462  UR    de   0    no_match  0.10 ok                                   3104   Bericht und Antrag RR an LR zur Aufgabenüberprüf
227143  VD    fr   0    no_match  0.00 ok                     yes    yes    2042   Rapport annuel 2022 de la commission interparlem
227186  VD    fr   0    no_match  0.00 ok                     yes           4017   Élection complémentaire d’un assesseur à la Cour
331397  VD    fr   0    no_match  0.00 ok                     yes    yes    3300   Exposé des motifs et projet de loi sur la rémuné
91286   ZH    de   0    no_match  0.00 ok                     yes           4793   Konfliktpotenzial im Kinder- und Jugendheimgeset

run 20261018T124304338082Z  model=apertus-v1-5-70b  prompt_version=3e7c090902c6 (adhoc_v2)  topic=Digitalisation
statuses: {'ok': 39, 'evidence_failed': 1}  (lang_missing excluded: 0)
positives → match:     14/20 = 70%  95% CI 48%–85%
negatives → not match: 19/20 = 95%  95% CI 76%–99%
accuracy (all):        33/40
evidence verified:     14/15 model matches = 93%
keyword-absent matches: 0 (gold positive 0, gold negative 0)
latency p50/p95: 3856/5818 ms   tokens in/out: 97,866/5,040

truncated: 15/40
   173404 TI    cut in DOCUMENT (Strategia per la trasformazione digitale del Canto lost 379,081 of 391,081 chars
   182664 OW    cut in DOCUMENT (Botschaft zum Nachtrag kDSG)                       lost 225,892 of 237,892 chars
   336119 OW    cut in DOCUMENT (Geschäftsbericht_VSZ)                              lost 176,993 of 188,993 chars
   200462 UR    cut in DOCUMENT (LA.2018-0512 II. Beilage zu Bericht des Regierungs lost 113,614 of 125,614 chars
    85111 TI    cut in DOCUMENT (Rapporto)                                          lost  87,095 of  99,095 chars
   201152 AR    cut in DOCUMENT (Beilage 1.1 Geschäftsbericht und Jahresrechnung 20 lost  79,109 of  91,109 chars
   286923 JU    cut in DOCUMENT (Réorganisation du Service juridique et du Service  lost  67,789 of  79,789 chars
    77719 OW    cut in DOCUMENT (Bericht zur Digitalstrategie 2025-2028)            lost  36,944 of  48,944 chars
   216730 NE    cut in DOCUMENT (22.155: Politique de subventionnement, l’État est- lost   6,606 of  18,606 chars
    83985 TI    cut in DOCUMENT (Risposta del CdS del 28.08.2019)                   lost   6,087 of  18,087 chars
   173899 TI    cut in DOCUMENT (Risposta del CdS del 19.02.2025)                   lost   4,571 of  16,571 chars
   226793 VD    cut in DOCUMENT (Registre des automobiles et sécurité des données)  lost   3,435 of  15,435 chars
   227082 VD    cut in DOCUMENT (Texte adopté par CE - R-CE INT Mocchi 23_INT_51- p lost   2,487 of  14,487 chars
   229042 VD    cut in DOCUMENT (EMPD autorisant l'accès de la Policlinique médical lost   2,258 of  14,258 chars
    91286 ZH    cut in DOCUMENT (Antwort_RR_399-2022_Konfliktpotenzial_im_Kinder-_u lost     554 of  12,554 chars

vs run 20261018T124225649726Z (prompt parts changed: ['topic'])
changed: 4
   156184 gold=1 match/ok → no_match/ok  [broke]  Garantire la partecipazione e la diversità cultura
   234879 gold=1 no_match/ok → match/ok  [fixed]  Recherche automatisée de véhicules et surveillance
   216800 gold=1 match/ok → no_match/ok  [broke]  Inventaire électronique des installations d’approv
   234707 gold=0 no_match/ok → abstain/ok  [same outcome]  Dienstpflicht der Zukunft

=== old draft definition
run 20261018T124225649726Z  model=apertus-v1-5-70b  prompt_version=f5aca487d27c (adhoc_v2)  topic=Digitalisation
statuses: {'ok': 39, 'evidence_failed': 1}  (lang_missing excluded: 0)
positives → match:     15/20 = 75%  95% CI 53%–89%
negatives → not match: 19/20 = 95%  95% CI 76%–99%
accuracy (all):        34/40
evidence verified:     15/16 model matches = 94%
keyword-absent matches: 6 (gold positive 6, gold negative 0)
latency p50/p95: 3602/5195 ms   tokens in/out: 87,626/4,752
```

## Truncated affairs re-run at MAX_INPUT_CHARS=40000 (run 20261018T124418349670Z, prompt_version 8f487e483cda)

15 truncated affairs: label/status changed 2 (77719 match→evidence_failed [worse], 336119 evidence_failed→no_match [better]); evidence-only changes 10; input tokens 54,692 → 120,194. Same 15 at 12k again (run 20261018T124505142790Z): 0 label changes, 1 evidence change.

## adhoc_v3 + core keywords (prompt_version d420fc57afb3), stored in SQLite (S5)

Run 20261018T130959024927Z (and an identical repeat 20261018T130918500286Z, 0 changes):
positives 14/20 (70%, CI 48–85%), negatives 20/20 (100%, CI 84–100%), evidence verified 14/14, keyword-absent matches 6 (all gold positive; 0 also tech-vocab-absent), abstain 1, inconsistent 1 (156184: no_match at 0.6).
vs adhoc_v2 run 20261018T124304338082Z: 1 change — 336119 (gold no) match/evidence_failed → no_match/ok [fixed].
