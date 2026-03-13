# Telegram MiniApp Geo-Radar PRD

## Project Overview
Signal Intelligence System - Telegram MiniApp для моніторингу та звітування про події в місті в реальному часі.

**Repository:** https://github.com/ventureguro-create/fdfdfdfdf
**Preview URL:** https://9d9c303b-fa4e-4bb3-975f-22fe7bfee738.preview.emergentagent.com

## Architecture
- **Frontend:** React 19 + Leaflet + Zustand + Tailwind CSS
- **Backend:** FastAPI + MongoDB (motor async driver)
- **Telegram Bot Token:** 8186116561:AAGPwRpPTJ-rvwebP487lCtCBOcAvPmI6Oc

---

## What's Been Implemented

### 2026-03-13: Initial Setup
- ✅ Клоновано репозиторій з GitHub
- ✅ Налаштовано backend (FastAPI) на порту 8001
- ✅ Налаштовано frontend (React) на порту 3000
- ✅ MongoDB підключено та працює

### 2026-03-13: Event Builder Engine (MAIN FEATURE)

#### 1. Dedup Engine ✅
Об'єднання сигналів за умови:
- distance < 300m
- type однаковий
- час < 20 min

**Приклад:**
```
3 сообщения про БП на Житомирській → 1 EVENT (reports: 3, confidence: 0.87)
```

#### 2. Confidence Formula ✅
```
event_confidence = 
    ai_confidence * 0.30
    + reports_weight * 0.25
    + sources_weight * 0.20
    + recency_weight * 0.15
    + user_confirmations * 0.10
    + photo_bonus (+0.15)
    - location_unknown_penalty (-0.20)
```

#### 3. Signal Decay ✅
- TTL продовжується при нових репортах (+10 хвилин)
- Кожен тип сигналу має свій TTL (detention: 120min, police: 45min, etc.)

#### 4. Negative Filter ✅
Словник негативних слів:
```
чисто, вільно, пусто, розійшлись, немає, clear, gone, empty...
```
Якщо повідомлення містить → confidence падає / event закривається

#### 5. Event Status Lifecycle ✅
```
candidate  (1 сигнал)
correlated (2 сигнала)
verified   (2+ sources, confidence > 0.65)
expired    (TTL закінчився)
dismissed  (модерація / негативні репорти)
```

#### 6. Event Strength ✅
```
weak     - 1 джерело
medium   - 2 сигнали / 1-2 джерела
strong   - 3+ джерела
critical - detention/raid + фото + підтвердження
```

#### 7. Signal Reports Table ✅
```
geo_signal_reports:
- report_id
- event_id
- source_channel
- original_text
- ai_confidence
- has_photo
- created_at
```

#### 8. Signal Priority ✅
```
detention: 0.90, raid: 0.85, checkpoint: 0.80
police: 0.75, danger: 0.80, fire: 0.90
accident: 0.75, virus: 0.70, weather: 0.50
```

---

## API Endpoints

### Event Builder API
```
GET  /api/geo/events                    - Deduplicated events
GET  /api/geo/events/{id}               - Event details + reports
GET  /api/geo/events/config/info        - Configuration
GET  /api/geo/events/stats              - Statistics
POST /api/geo/events/process-signal     - Create/merge signal
POST /api/geo/events/{id}/confirm       - User confirms
POST /api/geo/events/{id}/not-there     - User reports gone
POST /api/geo/events/expire-old         - Expire TTL events
GET  /api/geo/signal-reports            - Signal reports table
POST /api/geo/test/negative-filter      - Test negative filter
POST /api/geo/test/confidence-calc      - Test confidence calc
```

### Existing API
```
GET  /api/geo/map
GET  /api/geo/heatmap  
GET  /api/geo/radar
POST /api/geo/miniapp/report
```

---

## File Structure
```
/app/
├── backend/
│   ├── server.py
│   ├── .env
│   └── geo_intel/
│       ├── router.py                 # API routes
│       ├── module.py
│       └── services/
│           ├── event_builder.py      # NEW: Event Builder Engine
│           ├── ai_signal_classifier.py
│           ├── signal_decay.py
│           ├── fusion_engine.py
│           └── ...
├── frontend/
│   ├── .env
│   └── src/miniapp/
│       ├── MiniApp.jsx
│       ├── stores/appStore.js        # Updated with Events API
│       └── components/
│           ├── EventCard.jsx         # NEW: Event display
│           └── ...
└── memory/
    └── PRD.md
```

---

## Testing Results (2026-03-13)

### Event Builder Tests ✅
| Test | Result |
|------|--------|
| Create event | ✅ `action: created`, status: candidate |
| Merge signal (300m) | ✅ `action: merged`, reports++ |
| 3 sources → strong | ✅ strength: strong, confidence: 0.89 |
| Negative filter | ✅ "gone" detected, penalty: 0.15 |
| Confidence calc | ✅ Formula working correctly |
| Signal reports | ✅ 6 reports linked to events |
| Event stats | ✅ by_status, by_type, avg_confidence |

---

## Prioritized Backlog

### P0 (Critical) - DONE ✅
- [x] Event Builder Engine
- [x] Dedup Engine (300m/20min)
- [x] Confidence Formula
- [x] Signal Decay + TTL extension
- [x] Negative Filter
- [x] Event Status lifecycle
- [x] Signal Reports table
- [x] API endpoints

### P1 (High Priority) - TODO
- [ ] MTProto String Session integration
- [ ] Admin Panel: AI Engine settings tab
- [ ] Real-time Telegram alerts for verified events
- [ ] Map показує events замість raw signals

### P2 (Medium Priority)
- [ ] Location normalization (Житомирська трасса → normalized)
- [ ] Source weighting (trusted_channel: 0.8, new_channel: 0.5)
- [ ] Photo verification bonus
- [ ] Pattern detection (AI Alert)

### P3 (Future)
- [ ] AI entity extraction (vehicle, color, plate)
- [ ] Safe route planning
- [ ] Multi-location messages

---

## Environment Variables

### Backend (.env)
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=telegram_intel
BOT_TOKEN=8186116561:AAGPwRpPTJ-rvwebP487lCtCBOcAvPmI6Oc
CHANNEL_ID=@ARKHOR
```

### Frontend (.env)
```
REACT_APP_BACKEND_URL=https://9d9c303b-fa4e-4bb3-975f-22fe7bfee738.preview.emergentagent.com
```

---

## Pipeline Architecture

```
Telegram Parser
     ↓
Slang Normalizer
     ↓
Keyword Filter
     ↓
AI Classifier
     ↓
Location Extractor
     ↓
Geocoder
     ↓
Signal Engine
     ↓
EVENT BUILDER ← NEW!
     ↓
Radar Map / Alerts
```

---

*Last updated: 2026-03-13*
