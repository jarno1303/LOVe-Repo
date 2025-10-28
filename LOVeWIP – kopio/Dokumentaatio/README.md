# LOVe Enhanced - Lääkehoidon oppimisalusta

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-green.svg)
![License](https://img.shields.io/badge/license-Proprietary-red.svg)
![Status](https://img.shields.io/badge/status-MVP-orange.svg)

**LOVe Enhanced** on moderni, pedagogisesti edistynyt oppimisalusta lähihoitajien lääkehoidon osaamisen kehittämiseen. Sovellus hyödyntää Spaced Repetition -algoritmia, gamifikaatiota ja kattavaa analytiikkaa optimaalisen oppimiskokemuksen tarjoamiseksi.

## 🌟 Ominaisuudet

### 📚 Oppiminen
- **340+ kysymystä** 10 eri kategoriassa
- **Spaced Repetition (SM-2)** - tieteellisesti perusteltu kertausjärjestelmä
- **Älykäs kertaus** - järjestelmä ehdottaa oikeaan aikaan kertauskysymyksiä
- **3 vaikeustasoa** - helppoja, keskivaikeita ja vaikeita kysymyksiä
- **Yksityiskohtaiset selitykset** - jokaiseen kysymykseen

### 🎮 Gamifikaatio
- **16 saavutusta** - motivoi jatkuvaan oppimiseen
- **Pisteytys ja tilastot** - seuraa edistymistäsi
- **Streak-järjestelmä** - palkitsee päivittäisestä harjoittelusta
- **Kategoriakohtainen edistyminen** - näe vahvuutesi ja heikkoutesi

### 📊 Analytiikka
- **Yksityiskohtaiset tilastot** - onnistumisprosentit kategorioi
- **Edistymisen seuranta** - visuaaliset graafit
- **Personoidut suositukset** - järjestelmä ohjaa heikkoihin alueisiin
- **Oppimishistoria** - katso kaikki vastauksesi

### 🎯 Erikoisominaisuudet
- **Koesimulaatio** - tee täysimittainen 50 kysymyksen testi
- **Häiriötekijät** - simuloi todellisia työtilanteita
- **Admin-paneeli** - opettajille hallintaan ja sisällöntuotantoon
- **Käyttäjäroolit** - opiskelija, opettaja, admin

## 🚀 Pika-aloitus

### Esivalmistelut

**Vaatimukset:**
- Python 3.8 tai uudempi
- pip (Python package manager)
- SQLite (kehitykseen) tai PostgreSQL (tuotantoon)

### Asennus

1. **Kloonaa repositorio:**
```bash
git clone https://github.com/yourusername/love-enhanced.git
cd love-enhanced
```

2. **Luo virtuaaliympäristö:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# tai
venv\Scripts\activate  # Windows
```

3. **Asenna riippuvuudet:**
```bash
pip install -r requirements.txt
```

4. **Luo ympäristömuuttujat:**
```bash
cp .env.example .env
# Muokkaa .env-tiedostoa tarpeidesi mukaan
```

5. **Alusta tietokanta:**
```bash
python init_db.py
```

6. **Käynnistä sovellus:**
```bash
python app.py
```

7. **Avaa selaimessa:**
```
http://localhost:5000
```

### Oletuskäyttäjät (kehitysympäristö)

| Käyttäjätunnus | Salasana | Rooli |
|----------------|----------|-------|
| admin | admin123 | Admin |
| opettaja | opettaja123 | Opettaja |
| opiskelija | opiskelija123 | Opiskelija |

⚠️ **HUOM:** Vaihda nämä tuotantoympäristössä!

## 📁 Projektin rakenne

```
love-enhanced/
├── app.py                  # Pääsovellus ja reitit
├── database_manager.py     # Tietokantahallinta
├── models/
│   └── models.py          # Datamallit
├── logic/
│   ├── achievement_manager.py    # Saavutusjärjestelmä
│   ├── spaced_repetition.py      # SR-algoritmi
│   ├── stats_manager.py          # Tilastot
│   └── simulation_manager.py     # Simulaatiot
├── templates/              # HTML-sivupohjat
│   ├── base.html
│   ├── dashboard.html
│   ├── practice.html
│   ├── review.html
│   ├── stats.html
│   ├── simulation.html
│   └── admin/
│       └── ...
├── static/                 # CSS, JS, kuvat
├── data/
│   └── questions.db       # Kysymystietokanta
├── requirements.txt       # Python-riippuvuudet
└── README.md
```

## 🛠️ Teknologiat

### Backend
- **Flask 3.0** - Web-framework
- **SQLite/PostgreSQL** - Tietokanta
- **Flask-Login** - Autentikaatio
- **WTForms** - Lomakkeiden käsittely
- **Werkzeug** - Salasanojen hajautus

### Frontend
- **Bootstrap 5.3** - UI-framework
- **Font Awesome 6** - Ikonit
- **JavaScript (Vanilla)** - Interaktiivisuus
- **Chart.js** - Tilastograafit

### Algoritmit
- **SM-2 (Spaced Repetition)** - SuperMemo 2 -algoritmi
- **Achievement System** - Gamifikaatio
- **Analytics Engine** - Oppimisanalytiikka

## 📊 Tietokanta

### Keskeiset taulut

- `users` - Käyttäjätiedot
- `questions` - Kysymyspankki
- `question_attempts` - Vastaushistoria
- `user_question_progress` - Käyttäjäkohtainen edistyminen
- `user_achievements` - Avatut saavutukset
- `study_sessions` - Opiskelusessiot
- `simulation_results` - Kokeiden tulokset
- `distractor_attempts` - Häiriötekijävastaukset

**Katso tarkempi dokumentaatio:** [DATABASE.md](docs/DATABASE.md)

## 🔒 Tietoturva

- **CSRF-suojaus** - WTForms
- **Salasanojen hajautus** - bcrypt via Werkzeug
- **SQL Injection -suojaus** - Parametrisoidut kyselyt
- **Session-hallinta** - Flask-Login
- **Käyttäjäroolit** - Admin/Opettaja/Opiskelija

**Tuotantosuositukset:** [SECURITY.md](docs/SECURITY.md)

## 📖 Dokumentaatio

- [API-dokumentaatio](docs/API.md) - RESTful endpoint-kuvaukset
- [Kehittäjäohjeet](docs/DEVELOPER.md) - Arkkitehtuuri ja koodin rakenne
- [Käyttöohjeet](docs/USER_GUIDE.md) - Opiskelijoille ja opettajille
- [Deployment-ohjeet](docs/DEPLOYMENT.md) - Tuotantoon vienti
- [Tietokantakaavio](docs/DATABASE.md) - Tietokantarakenne
- [Changelog](CHANGELOG.md) - Versiohistoria

## 🧪 Testaus

### Yksikkötestit (tulossa)
```bash
pytest tests/
```

### Manuaalinen testaus
1. Rekisteröidy uutena käyttäjänä
2. Vastaa 20 kysymykseen
3. Tarkista tilastot
4. Kokeile kertausjärjestelmää
5. Tee koesimulaatio

## 🚀 Tuotantoon vienti

### 1. Ympäristömuuttujat
```bash
FLASK_ENV=production
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

### 2. Tietoturva
- Käytä HTTPS:ää
- Aseta vahva SECRET_KEY
- Ota käyttöön rate limiting
- Konfiguroi CORS

### 3. Palvelimet (suositukset)
- **Sovellus:** Gunicorn + Nginx
- **Tietokanta:** PostgreSQL
- **Hosting:** DigitalOcean, AWS, Azure, Render

**Tarkemmat ohjeet:** [DEPLOYMENT.md](docs/DEPLOYMENT.md)

## 📈 Jatkokehitys (Roadmap)

### Q1 2026 - Pilotti
- [ ] 2-3 pilottioppilaitosta
- [ ] Käyttäjäpalaute
- [ ] Bugien korjaukset

### Q2-Q4 2026 - Kasvu
- [ ] Mobiilisovellus (React Native)
- [ ] Lisää sisältöä (+115 kysymystä)
- [ ] Sosiaalinen oppiminen
- [ ] Video-oppimateriaali

### 2027+ - Skaalaus
- [ ] Kansainvälistyminen (Ruotsi)
- [ ] White Label -ratkaisut
- [ ] Täydennyskoulutusmarkkina

## 🤝 Yhteistyö ja tuki

### Osallistuminen
Sovellus on tällä hetkellä suljettu kehitysvaiheessa. Jos haluat osallistua:
- Ota yhteyttä: [email@example.com]

### Tuki
- **Dokumentaatio:** [docs/](docs/)
- **Issues:** [GitHub Issues](https://github.com/yourusername/love-enhanced/issues)
- **Sähköposti:** support@loveenhanced.fi

## 📄 Lisenssi

Proprietary License - Kaikki oikeudet pidätetään.

Tämä ohjelmisto on suojattu tekijänoikeuslailla. Luvaton käyttö, kopiointi, muokkaaminen tai jakelu on kielletty ilman kirjallista lupaa.

**© 2025 LOVe Enhanced. Kaikki oikeudet pidätetään.**

## 🙏 Kiitokset

- **Oppilaitokset** - Pilottiasiakkaat ja palautteen antajat
- **Opiskelijat** - Testaajat ja käyttäjät
- **Flask-yhteisö** - Erinomainen framework
- **SuperMemo** - SM-2 algoritmi

## 📞 Yhteystiedot

- **Verkkosivut:** https://loveenhanced.fi (tulossa)
- **Sähköposti:** info@loveenhanced.fi
- **LinkedIn:** [LOVe Enhanced](https://linkedin.com/company/love-enhanced)

---

**Tehty ❤️:llä suomalaisille hoitajille**
