# 🎶 PG Pitigliano App — Canzoniere Diocesano Digitale

[![Web App](https://img.shields.io/badge/Live_App-tvicxx.github.io%2Fpg--pitigliano--app-blue?style=for-the-badge&logo=github)](https://tvicxx.github.io/pg-pitigliano-app)
[![Diocesi](https://img.shields.io/badge/Diocesi-Pitigliano--Sovana--Orbetello-darkgreen?style=for-the-badge)](https://www.diocesipitigliano.it)
[![Pastorale Giovanile](https://img.shields.io/badge/Ambito-Pastorale_Giovanile-orange?style=for-the-badge)](#)

> **Un unico punto di riferimento digitale per i canti liturgici e comunitari della Diocesi di Pitigliano-Sovana-Orbetello.**

---

## 📌 Cos'è questo progetto?

**PG Pitigliano App** è una webapp nata originariamente per le attività, gli incontri e le celebrazioni della **Pastorale Giovanile della Diocesi di Pitigliano-Sovana-Orbetello**.

L'idea alla base del progetto risponde a un'esigenza concreta e condivisa da educatori, cori e comunità: **avere un aggregatore unico, moderno e facilmente accessibile per tutti i canti di chiesa**. Spesso testi, accordi e spartiti sono frammentati tra fogli volanti, canzonieri cartacei ormai datati o file sparsi su diverse piattaforme. Questa applicazione nasce per centralizzare il repertorio e renderlo immediatamente fruibile da qualsiasi dispositivo (smartphone, tablet, PC).

---

## 🎯 Visione ed Estensione Diocesana

Sebbene sia nato all'interno del percorso della Pastorale Giovanile, l'obiettivo a medio-lungo termine è **estendere l'utilizzo della webapp a tutta la Diocesi di Pitigliano-Sovana-Orbetello e a tutti i suoi enti**:
- ⛪ **Parrocchie e Comunità parrocchiali** (per animare messe domenicali, feste patronali e celebrazioni ordinarie)
- 🎼 **Cori parrocchiali e animatori liturgici**
- 🏕️ **Oratori, gruppi scout, associazioni e movimenti ecclesiali**
- 🏛️ **Uffici e commissioni diocesane** (liturgia, catechesi, famiglia, ecc.)

La piattaforma mira a diventare uno strumento di comunione diocesana, facilitando la condivisione di repertori comuni, nuovi brani e scalette liturgiche tra tutte le parrocchie del territorio diocesano.

---

## ✨ Funzionalità Principali

- 🔍 **Ricerca Rapida e Intelligente:** Ricerca immediata dei canti per titolo, testo, autore o momento liturgico.
- 📖 **Catalogo Organizzato:** Suddivisione dei canti per tempi liturgici (Avvento, Natale, Quaresima, Pasqua, Tempo Ordinario) e momenti della celebrazione (Ingresso, Gloria, Salmo, Offertorio, Santo, Comunione, Congedo).
- 🎸 **Testi e Accordi:** Visualizzazione chiara e leggibile anche su schermi di smartphone durante prove e celebrazioni.
- 📱 **Mobile-First & PWA:** Progettata per essere utilizzata ovunque, con interfaccia responsive e intuitiva.
- 📂 **Scalette e Raccolte:** Strumenti dedicati per organizzare i canti per specifici eventi, ritiri, veglie e celebrazioni.

---

## 🚀 Accesso alla WebApp

La webapp è accessibile pubblicamente via browser al seguente indirizzo:

👉 **[tvicxx.github.io/pg-pitigliano-app](https://tvicxx.github.io/pg-pitigliano-app)**

---

## 🛠️ Tecnologie Utilizzate

- **Frontend:** HTML5, CSS3, JavaScript / Framework Moderno
- **Hosting & CI/CD:** GitHub Pages
- **Dati:** Struttura modulare per l'inserimento standardizzato di testi, accordi e metadati

---

## 📖 Liturgia del giorno automatica

La scheda **Liturgia del Giorno** mostra la Messa del giorno (letture, salmo, Vangelo e preghiere) presa dal sito ufficiale della CEI, [chiesacattolica.it](https://www.chiesacattolica.it/liturgia-del-giorno/).

- Ogni mercoledì il workflow `.github/workflows/aggiorna-liturgia.yml` esegue `scripts/fetch_liturgia.py`, che scarica i prossimi 14 giorni e li salva in `liturgia.json`: se un aggiornamento salta, restano comunque almeno 7 giorni di margine.
- Nella scheda un menu in alto permette di scegliere uno qualsiasi dei giorni scaricati; se un giorno ha più messe (per esempio il 2 novembre o le memorie facoltative) compare un secondo menu per sceglierla.
- La webapp legge solo `liturgia.json` (nessuna API esterna a runtime) e, grazie al service worker, lo tiene anche per l'uso offline.
- Per aggiornare subito: scheda **Actions** → *Aggiorna liturgia del giorno* → **Run workflow**.
- Per provarlo in locale: `python3 scripts/fetch_liturgia.py` (richiede solo Python 3.9+).

---

## 🗺️ Roadmap & Sviluppi Futuri

- [ ] **Modalità Offline (PWA):** Consultazione del canzoniere anche in chiese o luoghi con scarsa connettività.
- [ ] **Trasposizione Tonalità:** Cambio automatico della tonalità degli accordi con un click.
- [ ] **Esportazione & Condivisione:** Creazione automatica di libretti per celebrazioni speciali.
- [ ] **Portale Contributi Diocesano:** Sezione dedicata ai cori delle parrocchie diocesane per suggerire o caricare nuovi canti.

---

## 🤝 Come Contribuire

Il progetto è aperto alla collaborazione di educatori, musicisti, giovani e chiunque voglia dare una mano:
1. **Segnalazione correzioni o aggiunta canti:** Apri una [Issue](https://github.com/tvicxx/pg-pitigliano-app/issues) o contatta il referente del progetto.
2. **Sviluppo software:** Fai un fork del repository, crea un branch con la tua feature (`git checkout -b feature/nuova-funzione`) e invia una Pull Request.

---

## 📬 Contatti e Riferimenti

- **Servizio per la Pastorale Giovanile** — Diocesi di Pitigliano-Sovana-Orbetello
- **Sito Diocesano:** [www.diocesipitigliano.it](https://www.diocesipitigliano.it)
- **Repository GitHub:** [tvicxx/pg-pitigliano-app](https://github.com/tvicxx/pg-pitigliano-app)