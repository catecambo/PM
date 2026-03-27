# Analisi dei dati PM2.5 / PM10 da sensore Nova SDS011 (Sensor.Community)

## Introduzione

Questo progetto costruisce una pipeline di elaborazione dati per analizzare misure di qualità dell’aria provenienti da un sensore **Nova SDS011** collegato a un **ESP8266 NodeMCU** con firmware **Sensor.Community** (ex Luftdaten).

I dati provengono da file CSV scaricati dal mirror pubblico:
https://api-rrd.madavi.de/csvfiles.php?sensor=esp8266-3459560
```
madavi.de
```

con frequenza media:

```
≈ 1 campione ogni 160 secondi
≈ 22 campioni/ora
≈ 541 campioni/giorno
```

L’obiettivo della pipeline è produrre dataset aggregati:

* orari
* giornalieri
* mensili

scientificamente coerenti con:

* linee guida WHO 2021
* normativa UE attuale
* futura normativa UE 2030
* limiti tecnici del sensore SDS011
* fenomeni fisici atmosferici reali

---

# Il sensore: Nova SDS011

Il **Nova SDS011** è un sensore ottico a diffusione laser per particolato atmosferico.
http://en.novasensor.cn/?list_16/55.html

Misura:

| Variabile | Significato | Unità |
| --------- | ----------- | ----- |
| SDS_P2    | PM2.5       | μg/m³ |
| SDS_P1    | PM10        | μg/m³ |

Dashboard con i dati in tempo reale:
https://api-rrd.madavi.de:3000/grafana/d/GUaL5aZMz/pm-sensors?orgId=1&theme=light&var-chipID=esp8266-3459560&var-type=DHT22&var-query0=sensors&from=now-6h&to=now&timezone=browser

Sensor community map:
https://maps.sensor.community/#14/44.5152/11.3344

Metodo di misura:

```
laser scattering
```

Range operativo:

```
0 – 999 μg/m³
```

Risoluzione:

```
0.3 μg/m³
```

---

# Frequenza reale di campionamento

Il sensore produce 1 misura al secondo, ma il firmware Sensor.Community:

1. accende il laser
2. attende stabilizzazione
3. campiona
4. trasmette
5. sospende il sensore

Questo genera:

```
≈ 160 secondi tra campioni
≈ 22 campioni/ora
≈ 541 campioni/giorno
```

Motivazioni:

* ridurre consumo energetico
* aumentare durata laser (~8000 ore)
* ridurre riscaldamento interno

---

# Struttura dei dati in input

Le colonne principali utilizzate sono:

## Particolato

| Colonna | Significato |
| ------- | ----------- |
| SDS_P2  | PM2.5       |
| SDS_P1  | PM10        |

Sono le variabili principali per tutte le aggregazioni.

---

## Temperatura e umidità

Possibili colonne:

| Colonna  |
| -------- |
| Temp     |
| Humidity |

Servono per validazione qualità del particolato.

Motivazione:

oltre:

```
70% RH
```

il sensore confonde:

```
goccioline d'acqua
```

con:

```
particolato
```

---

## Diagnostica firmware

| Colonna   | Significato         |
| --------- | ------------------- |
| Signal    | potenza WiFi        |
| Samples   | contatore cicli ESP |
| Min_cycle | durata loop minima  |
| Max_cycle | durata loop massima |

Utilizzate per:

diagnostica qualità acquisizione.

---

# Pipeline di elaborazione

Pipeline completa:

```
CSV raw
↓
validazione PM
↓
aggregazione oraria
↓
aggregazione giornaliera
↓
aggregazione mensile
```

Ogni livello introduce:

* filtraggio qualità
* pesatura statistica
* stabilizzazione fisica del segnale

---

# Validazione preliminare del particolato

Definizione:

```
pm_valid
```

Una riga è valida se:

```
SDS_P2 != NaN
AND
Humidity < 70%
```

oppure:

```
Humidity non disponibile
```

Motivazione fisica:

oltre 70% RH:

```
laser scattering misura aerosol + acqua
```

quindi:

PM sovrastimato.

---

# Aggregazione oraria

L’aggregazione oraria trasforma:

```
22 campioni raw
```

in:

```
1 campione orario
```

---

# Perché aggregare su base oraria

Motivazioni principali:

## Riduzione rumore casuale

Il singolo campione SDS011 è influenzato da:

* turbolenza locale
* passaggio veicoli
* microvariazioni vento
* instabilità aerosol

La media oraria riduce:

```
errore casuale
```

---

## Compatibilità con reti ufficiali

Le stazioni ARPA lavorano su:

```
medie orarie
```

---

## Separazione fenomeni atmosferici

Scala oraria distingue:

| fenomeno           | scala |
| ------------------ | ----- |
| traffico           | ore   |
| riscaldamento      | ore   |
| inversione termica | ore   |
| ventilazione       | ore   |

---

# Statistiche orarie calcolate

Per PM2.5:

```
pm25_mean
pm25_max
pm25_median
pm25_std
```

Per PM10:

```
pm10_mean
pm10_max
```

---

# Significato statistico delle metriche

| metrica | significato             |
| ------- | ----------------------- |
| mean    | valore normativo        |
| median  | robusta agli outlier    |
| max     | eventi brevi            |
| std     | variabilità atmosferica |

---

# Perché usare la mediana

Serve per rilevare:

```
spike brevi
```

Esempio:

passaggio camion diesel

Risultato:

```
mean aumenta
median resta stabile
```

---

# Perché usare deviazione standard

Serve per identificare:

```
instabilità atmosferica
```

tipica di:

* traffico intenso
* turbolenza urbana
* combustione locale

---

# Filtraggio qualità oraria

Calcolati:

```
coverage_pct
pm_valid_pct
```

---

# coverage_pct

Formula:

```
campioni ricevuti / campioni attesi
```

Serve per identificare:

* perdita WiFi
* riavvii ESP
* errori trasmissione

---

# pm_valid_pct

Formula:

```
campioni validi / campioni ricevuti
```

Serve per identificare:

* nebbia
* condensa
* alta umidità

---

# Quality flag orario

Classificazione:

| stato   | significato       |
| ------- | ----------------- |
| good    | dati affidabili   |
| low_cov | pochi campioni    |
| humid   | troppa umidità    |
| bad     | entrambi problemi |
| no_data | nessun dato       |

---

# Rapporto PM2.5 / PM10

Definizione:

```
pm_ratio = PM2.5 / PM10
```

Interpretazione:

| valore  | sorgente           |
| ------- | ------------------ |
| >0.8    | combustione        |
| 0.5–0.8 | traffico urbano    |
| <0.5    | polveri grossolane |

---

# Aggregazione giornaliera

Produce:

```
1 valore/giorno
```

compatibile con:

* WHO
* normativa UE

---

# Perché non usare media semplice delle ore

Caso reale:

```
4 ore con 2 campioni
20 ore con 22 campioni
```

Media semplice:

peso identico

Media pesata:

peso proporzionale ai dati validi

Risultato:

più accurata.

---

# Media giornaliera pesata

Formula:

```
np.average(... weights=n_pm_valid)
```

Riduce bias da:

* perdita WiFi
* nebbia
* condensa
* dati mancanti

---

# Flag affidabilità giornaliera

Condizione:

```
≥ 18 ore good
```

Motivazione:

standard climatologico minimo:

```
75% copertura
```

---

# Metriche giornaliere aggiuntive

Calcolate:

```
hours_good_pct
coverage_pct
pm_valid_pct
pm_ratio
```

Servono per stimare:

qualità del giorno.

---

# Aggregazione mensile

Produce:

```
1 valore/mese
```

Serve per:

* trend stagionali
* confronto normativo
* analisi epidemiologica

---

# Media mensile pesata

Calcolata solo su:

```
giorni affidabili
```

Motivazione:

giorni incompleti falsano la media.

---

# Contatori giorni sopra soglia

Calcolati:

```
days_above_who_daily
days_above_eu_current
days_above_eu_2030
```

Servono per:

verifica normativa diretta.

---

# Perché contare giorni sopra soglia

Normativa UE PM10:

```
max 35 giorni/anno > 50 μg/m³
```

Serve quindi:

conteggio eventi

non solo media.

---

# Copertura mensile

Formula:

```
giorni affidabili / giorni totali
```

Serve per valutare:

qualità statistica mese.

---

# Classificazione WHO mensile

Funzione:

```
who_class()
```

Classi:

| classe     | significato |
| ---------- | ----------- |
| who_2021   | eccellente  |
| eu_2030    | buona       |
| who_daily  | moderata    |
| eu_current | critica     |
| above_all  | severa      |

---

# Perché la media è la metrica principale

WHO e UE definiscono limiti su:

```
medie aritmetiche
```

non su:

```
median
percentili
```

---

# Ruolo della mediana

Serve per individuare:

```
eventi locali brevi
outlier
picchi traffico
```

---

# Pesatura multilivello della pipeline

Sequenza:

```
campione → ora
ora → giorno
giorno → mese
```

Garantisce:

* coerenza normativa
* robustezza statistica
* qualità citizen-science elevata

---

# Output finali prodotti

La pipeline genera:

```
hourly_aggregated.csv
daily_aggregated.csv
monthly_aggregated.csv
```

Utilizzabili per:

* Power BI
* Python analytics
* dashboard ambientali
* confronto ARPA (https://www.bologna-airport.it/innovazione-e-sostenibilita/sostenibilita/ambiente-ed-energia/aria/?idC=62535)
* analisi traffico
* pattern stagionali
* verifica normativa WHO / UE (https://eur-lex.europa.eu/IT/legal-content/summary/quality-and-safety-of-substances-of-human-origin-intended-for-human-application.html)
