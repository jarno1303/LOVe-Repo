# API-dokumentaatio - LOVe Enhanced

Tämä dokumentti kuvaa LOVe Enhanced -sovelluksen REST API:n. API mahdollistaa ohjelmallisen pääsyn kysymyksiin, tilastoihin ja käyttäjätietoihin.

## 📋 Sisällysluettelo

- [Yleistä](#yleistä)
- [Autentikaatio](#autentikaatio)
- [Kysymykset](#kysymykset)
- [Vastaukset](#vastaukset)
- [Tilastot](#tilastot)
- [Saavutukset](#saavutukset)
- [Käyttäjähallinta](#käyttäjähallinta)
- [Admin-toiminnot](#admin-toiminnot)
- [Virheenkäsittely](#virheenkäsittely)

## Yleistä

### Base URL
```
Development: http://localhost:5000
Production:  https://api.loveenhanced.fi
```

### Vastausformaatti
Kaikki API-vastaukset ovat JSON-muodossa.

### Aikaleima-formaatti
ISO 8601: `YYYY-MM-DDTHH:MM:SS`

### Pagination
```json
{
  "page": 1,
  "per_page": 20,
  "total": 340,
  "pages": 17
}
```

## Autentikaatio

### Session-pohjainen autentikaatio

Sovellus käyttää Flask-Login session-pohjaista autentikaatiota. CSRF-token vaaditaan POST/PUT/DELETE-pyynnöissä.

**CSRF Token:**
```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
```

### Kirjautuminen

**POST** `/login`

Kirjaa käyttäjän sisään ja luo session.

**Request Body:**
```json
{
  "username": "opiskelija",
  "password": "salasana123"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "user_id": 1,
  "username": "opiskelija",
  "role": "user",
  "redirect": "/dashboard"
}
```

### Uloskirjautuminen

**POST** `/logout`

Kirjaa käyttäjän ulos ja tuhoaa session.

**Response:** `302 Redirect`
```
Location: /login
```

---

## Kysymykset

### Hae satunnaisia kysymyksiä

**GET** `/api/random-questions?count=20&category=Farmakologia`

Hakee satunnaisia kysymyksiä harjoittelua varten.

**Query Parameters:**
- `count` (optional, default: 20) - Kysymysten määrä
- `category` (optional) - Kategoria-suodatus
- `difficulty` (optional) - Vaikeustaso (helppo/keskivaikea/vaikea)

**Response:** `200 OK`
```json
{
  "questions": [
    {
      "id": 1,
      "question": "Mikä on parasetamolin maksimi vuorokausiannos aikuiselle?",
      "options": ["2g", "3g", "4g", "5g"],
      "correct": 2,
      "explanation": "Parasetamolin maksimi vuorokausiannos...",
      "category": "Farmakologia",
      "difficulty": "helppo",
      "hint_type": "calculation"
    },
    ...
  ],
  "total": 20
}
```

### Hae kertauskysymykset

**GET** `/api/review-questions?limit=20`

Hakee käyttäjän erääntyvät kertauskysymykset Spaced Repetition -algoritmin mukaan.

**Query Parameters:**
- `limit` (optional, default: 20) - Maksimimäärä

**Response:** `200 OK`
```json
{
  "question": {
    "id": 45,
    "question": "Kuinka usein insuliinilääkitys tulee tarkistaa?",
    "options": [...],
    "correct": 1,
    "explanation": "...",
    "category": "Diabeteslääkkeet",
    "difficulty": "keskivaikea",
    "times_shown": 3,
    "times_correct": 2,
    "ease_factor": 2.5,
    "interval": 7,
    "last_shown": "2025-10-17T14:30:00"
  },
  "distractor": {
    "scenario": "Olet juuri vastaamassa kysymykseen kun puhelimesi soi...",
    "options": ["Vastaa puhelimeen", "Hylkää puhelu", "Laita puhelin äänettömälle"],
    "correct": 2
  }
}
```

### Hae kysymyksen tiedot

**GET** `/api/questions/:id`

Hakee yksittäisen kysymyksen tiedot.

**Response:** `200 OK`
```json
{
  "id": 1,
  "question": "Mikä on parasetamolin maksimi vuorokausiannos aikuiselle?",
  "options": ["2g", "3g", "4g", "5g"],
  "correct": 2,
  "explanation": "Parasetamolin maksimi vuorokausiannos aikuiselle on 4 grammaa...",
  "category": "Farmakologia",
  "difficulty": "helppo",
  "created_at": "2025-01-15T10:00:00",
  "times_shown": 156,
  "times_correct": 142,
  "hint_type": "calculation"
}
```

---

## Vastaukset

### Lähetä vastaus

**POST** `/api/submit_answer`

Tallentaa käyttäjän vastauksen ja päivittää statistiikkaa.

**Request Body:**
```json
{
  "question_id": 1,
  "selected_option_text": "4g",
  "time_taken": 15,
  "csrf_token": "..."
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "correct": true,
  "explanation": "Oikein! Parasetamolin maksimi vuorokausiannos...",
  "new_achievements": ["first_steps"],
  "stats": {
    "total_attempts": 1,
    "correct_attempts": 1,
    "success_rate": 1.0,
    "current_streak": 1
  }
}
```

### Lähetä häiriötekijävastaus

**POST** `/api/submit_distractor`

Tallentaa käyttäjän reaktion häiriötekijään.

**Request Body:**
```json
{
  "scenario": "Puhelimesi soi...",
  "user_choice": 2,
  "response_time": 3500,
  "csrf_token": "..."
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "correct": true,
  "feedback": "Hyvä valinta! Keskittyminen on tärkeää..."
}
```

---

## Tilastot

### Hae käyttäjän tilastot

**GET** `/api/user-stats`

Hakee kirjautuneen käyttäjän kattavat oppimistilastot.

**Response:** `200 OK`
```json
{
  "general": {
    "answered_questions": 45,
    "total_questions_in_db": 340,
    "avg_success_rate": 0.82,
    "total_attempts": 67,
    "total_correct": 55,
    "avg_time_per_question": 18.5
  },
  "categories": [
    {
      "category": "Farmakologia",
      "attempts": 20,
      "success_rate": 0.85
    },
    {
      "category": "Diabeteslääkkeet",
      "attempts": 15,
      "success_rate": 0.73
    }
  ],
  "difficulties": [
    {
      "difficulty": "helppo",
      "attempts": 30,
      "success_rate": 0.93
    },
    {
      "difficulty": "keskivaikea",
      "attempts": 25,
      "success_rate": 0.80
    },
    {
      "difficulty": "vaikea",
      "attempts": 12,
      "success_rate": 0.58
    }
  ],
  "weekly_progress": [
    {
      "date": "2025-10-18",
      "questions_answered": 15,
      "corrects": 12
    },
    {
      "date": "2025-10-19",
      "questions_answered": 20,
      "corrects": 18
    }
  ],
  "streak": {
    "current_streak": 5,
    "longest_streak": 12
  }
}
```

### Hae suositukset

**GET** `/api/recommendations`

Hakee personoidut oppimissuositukset käyttäjän datan perusteella.

**Response:** `200 OK`
```json
{
  "recommendations": [
    {
      "type": "weakest_category",
      "title": "Keskity: Diabeteslääkkeet",
      "description": "Onnistumisprosenttisi on 68%. Harjoittele lisää.",
      "action": "practice_category",
      "priority": "high",
      "category": "Diabeteslääkkeet",
      "accuracy": 68.0
    },
    {
      "type": "simulation",
      "title": "Kokeile koesimulaatiota!",
      "description": "Olet vastannut yli 50 kysymykseen. Testaa osaamistasi!",
      "action": "start_simulation",
      "priority": "medium"
    }
  ]
}
```

---

## Saavutukset

### Hae käyttäjän saavutukset

**GET** `/api/achievements`

Hakee käyttäjän kaikki saavutukset (avatut ja lukitut).

**Response:** `200 OK`
```json
{
  "unlocked": [
    {
      "id": "first_steps",
      "name": "Ensimmäiset askeleet",
      "description": "Vastasit ensimmäiseen kysymykseen",
      "icon": "🌟",
      "unlocked": true,
      "unlocked_at": "2025-10-18T10:30:00"
    }
  ],
  "locked": [
    {
      "id": "dedicated",
      "name": "Omistautunut",
      "description": "Vastasit 100 kysymykseen",
      "icon": "📚",
      "unlocked": false,
      "progress": 45
    }
  ],
  "total": 16,
  "unlocked_count": 3,
  "percentage": 18.75
}
```

### Tarkista uudet saavutukset

**POST** `/api/check-achievements`

Tarkistaa ja avaa käyttäjälle uusia saavutuksia.

**Request Body:**
```json
{
  "context": {
    "simulation_perfect": true,
    "fast_answer": 4.5
  },
  "csrf_token": "..."
}
```

**Response:** `200 OK`
```json
{
  "new_achievements": [
    {
      "id": "speed_demon",
      "name": "Salamannopea",
      "description": "Vastasit kysymykseen alle 5 sekunnissa",
      "icon": "💨"
    }
  ]
}
```

---

## Käyttäjähallinta

### Rekisteröityminen

**POST** `/register`

Luo uuden käyttäjätilin.

**Request Body:**
```json
{
  "username": "uusiopiskelija",
  "email": "opiskelija@example.com",
  "password": "Salasana123!",
  "confirmPassword": "Salasana123!",
  "csrf_token": "..."
}
```

**Response:** `302 Redirect` tai `200 OK`
```json
{
  "success": true,
  "user_id": 123,
  "username": "uusiopiskelija",
  "message": "Rekisteröityminen onnistui!"
}
```

**Validointi:**
- Käyttäjänimi: 3-30 merkkiä, vain a-z, A-Z, 0-9, _
- Salasana: min. 8 merkkiä, iso kirjain, pieni kirjain, numero
- Sähköposti: validi sähköpostiosoite

### Profiilin päivitys

**POST** `/api/update-profile`

Päivittää käyttäjän asetuksia.

**Request Body:**
```json
{
  "distractors_enabled": true,
  "distractor_probability": 25,
  "csrf_token": "..."
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Asetukset päivitetty onnistuneesti"
}
```

### Salasanan vaihto

**POST** `/api/change-password`

Vaihtaa käyttäjän salasanan.

**Request Body:**
```json
{
  "current_password": "VanhaSalasana123!",
  "new_password": "UusiSalasana456!",
  "confirm_password": "UusiSalasana456!",
  "csrf_token": "..."
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Salasana vaihdettu onnistuneesti"
}
```

---

## Admin-toiminnot

### Hae kaikki käyttäjät (Admin)

**GET** `/api/admin/users?page=1&per_page=50`

Hakee listan kaikista käyttäjistä. Vaatii admin-roolin.

**Query Parameters:**
- `page` (optional, default: 1)
- `per_page` (optional, default: 50)
- `role` (optional) - Suodata roolin mukaan
- `status` (optional) - Suodata statuksen mukaan

**Response:** `200 OK`
```json
{
  "users": [
    {
      "id": 1,
      "username": "opiskelija1",
      "email": "opiskelija1@example.com",
      "role": "user",
      "status": "active",
      "created_at": "2025-09-15T10:00:00",
      "last_login": "2025-10-24T09:30:00",
      "total_attempts": 125,
      "success_rate": 0.84
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 234,
    "pages": 5
  }
}
```

### Lisää uusi kysymys (Admin)

**POST** `/api/admin/questions`

Lisää uuden kysymyksen tietokantaan. Vaatii admin-roolin.

**Request Body:**
```json
{
  "question": "Mikä on aspiriinin vaikutusmekanismi?",
  "options": [
    "Estää COX-1 ja COX-2 entsyymejä",
    "Estää tulehdussolujen kulkeutumista",
    "Vähentää prostaglandiinisynteesiä",
    "Kaikki yllä olevat"
  ],
  "correct": 3,
  "explanation": "Aspiriini estää syklo-oksygenaasi (COX) -entsyymejä...",
  "category": "Farmakologia",
  "difficulty": "keskivaikea",
  "hint_type": "mechanism",
  "csrf_token": "..."
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "question_id": 341,
  "message": "Kysymys lisätty onnistuneesti"
}
```

### Muokkaa kysymystä (Admin)

**PUT** `/api/admin/questions/:id`

Muokkaa olemassa olevaa kysymystä.

**Request Body:**
```json
{
  "question": "Päivitetty kysymysteksti",
  "explanation": "Päivitetty selitys",
  "difficulty": "vaikea",
  "csrf_token": "..."
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Kysymys päivitetty onnistuneesti"
}
```

### Poista kysymys (Admin)

**DELETE** `/api/admin/questions/:id`

Poistaa kysymyksen tietokannasta.

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Kysymys poistettu onnistuneesti"
}
```

### Tilastot (Admin)

**GET** `/api/admin/statistics`

Hakee järjestelmän laajuiset tilastot.

**Response:** `200 OK`
```json
{
  "users": {
    "total": 234,
    "active": 187,
    "inactive": 47,
    "new_this_month": 23
  },
  "questions": {
    "total": 340,
    "by_category": {
      "Farmakologia": 85,
      "Diabeteslääkkeet": 42,
      ...
    },
    "by_difficulty": {
      "helppo": 145,
      "keskivaikea": 152,
      "vaikea": 43
    }
  },
  "activity": {
    "total_attempts": 45678,
    "avg_success_rate": 0.78,
    "active_today": 45,
    "active_this_week": 156
  }
}
```

---

## Simulaatio

### Aloita simulaatio

**POST** `/api/simulation/start`

Aloittaa uuden koesimulaation.

**Request Body:**
```json
{
  "question_count": 50,
  "time_limit": 3600,
  "csrf_token": "..."
}
```

**Response:** `200 OK`
```json
{
  "simulation_id": 123,
  "questions": [...],
  "started_at": "2025-10-24T10:00:00",
  "time_limit": 3600
}
```

### Lopeta simulaatio

**POST** `/api/simulation/:id/complete`

Lopettaa simulaation ja tallentaa tulokset.

**Request Body:**
```json
{
  "answers": [
    {"question_id": 1, "selected": 2, "time_taken": 25},
    {"question_id": 5, "selected": 0, "time_taken": 18},
    ...
  ],
  "csrf_token": "..."
}
```

**Response:** `200 OK`
```json
{
  "simulation_id": 123,
  "score": 42,
  "total": 50,
  "percentage": 84.0,
  "time_taken": 2845,
  "passed": true,
  "detailed_results": [...]
}
```

---

## Virheenkäsittely

### HTTP-statuskoodit

| Koodi | Merkitys | Kuvaus |
|-------|----------|---------|
| 200 | OK | Pyyntö onnistui |
| 201 | Created | Resurssi luotu |
| 302 | Redirect | Uudelleenohjaus |
| 400 | Bad Request | Virheellinen pyyntö |
| 401 | Unauthorized | Autentikaatio vaaditaan |
| 403 | Forbidden | Ei oikeuksia |
| 404 | Not Found | Resurssia ei löydy |
| 409 | Conflict | Konflikti (esim. käyttäjänimi varattu) |
| 422 | Unprocessable Entity | Validointivirhe |
| 500 | Internal Server Error | Palvelinvirhe |

### Virhevastauksien muoto

```json
{
  "error": true,
  "message": "Virheellinen käyttäjänimi tai salasana",
  "code": "INVALID_CREDENTIALS",
  "details": {
    "field": "password",
    "reason": "Salasana on liian lyhyt"
  }
}
```

### Yleiset virhekoodit

| Koodi | Selitys |
|-------|---------|
| `INVALID_CREDENTIALS` | Väärä käyttäjänimi tai salasana |
| `UNAUTHORIZED` | Kirjautuminen vaaditaan |
| `FORBIDDEN` | Ei oikeuksia toimintoon |
| `NOT_FOUND` | Resurssia ei löydy |
| `VALIDATION_ERROR` | Validointivirhe |
| `DUPLICATE_USERNAME` | Käyttäjänimi varattu |
| `CSRF_ERROR` | CSRF-tokenin virhe |
| `DATABASE_ERROR` | Tietokantavirhe |

---

## Rate Limiting

API:ssa on rate limiting estämään väärinkäyttöä:

- **Yleinen:** 1000 pyyntöä / tunti / IP
- **Kirjautuminen:** 10 yritystä / 15 minuuttia / IP
- **Rekisteröityminen:** 5 rekisteröintiä / tunti / IP

**Rate Limit Headers:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1698156000
```

---

## Versiointi

API noudattaa semanttista versiointia (Semantic Versioning).

**Nykyinen versio:** `v1.0.0`

Tulevissa versioissa:
- `v1.x.x` - Pienet päivitykset, yhteensopivat
- `v2.x.x` - Suuret muutokset, mahdollisesti ei-yhteensopivia

---

## Esimerkkipyyntöjä

### cURL

```bash
# Kirjautuminen
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "opiskelija", "password": "salasana123"}'

# Hae satunnaisia kysymyksiä
curl -X GET http://localhost:5000/api/random-questions?count=10 \
  -H "Cookie: session=..."

# Lähetä vastaus
curl -X POST http://localhost:5000/api/submit_answer \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -d '{"question_id": 1, "selected_option_text": "4g", "time_taken": 15}'
```

### JavaScript (Fetch)

```javascript
// Hae kysymyksiä
async function getQuestions() {
  const response = await fetch('/api/random-questions?count=20');
  const data = await response.json();
  return data.questions;
}

// Lähetä vastaus
async function submitAnswer(questionId, answer, timeTaken) {
  const response = await fetch('/api/submit_answer', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': document.querySelector('[name=csrf_token]').value
    },
    body: JSON.stringify({
      question_id: questionId,
      selected_option_text: answer,
      time_taken: timeTaken
    })
  });
  return await response.json();
}
```

### Python (requests)

```python
import requests

# Kirjautuminen
session = requests.Session()
response = session.post('http://localhost:5000/login', json={
    'username': 'opiskelija',
    'password': 'salasana123'
})

# Hae kysymyksiä
questions = session.get('http://localhost:5000/api/random-questions?count=10').json()

# Lähetä vastaus
result = session.post('http://localhost:5000/api/submit_answer', json={
    'question_id': 1,
    'selected_option_text': '4g',
    'time_taken': 15
}).json()
```

---

## Yhteystiedot

**Tuki:** api-support@loveenhanced.fi  
**Dokumentaatio:** https://docs.loveenhanced.fi  
**Status:** https://status.loveenhanced.fi

**Versio:** 1.0.0  
**Viimeksi päivitetty:** 24.10.2025
