# Telegram MiniApp Geo-Radar PRD

## Project Overview
Telegram MiniApp для моніторингу та звітування про події в місті в реальному часі. Privacy-first підхід з автоматичним видаленням даних.

**Repository:** https://github.com/ventureguro-create/fdfdfdfdf
**Preview URL:** https://9d9c303b-fa4e-4bb3-975f-22fe7bfee738.preview.emergentagent.com

## Architecture
- **Frontend:** React 19 + Leaflet + Zustand + Tailwind CSS
- **Backend:** FastAPI + MongoDB (motor async driver)
- **Telegram Bot Token:** 8186116561:AAGPwRpPTJ-rvwebP487lCtCBOcAvPmI6Oc
- **Channel:** @ARKHOR

## User Personas
1. **Mobile User** - використовує MiniApp через Telegram
2. **Reporter** - повідомляє про сигнали (небезпека, поліція, погода і т.д.)
3. **Viewer** - переглядає карту сигналів в реальному часі
4. **Channel Subscriber** - отримує оповіщення в Telegram каналі

---

## What's Been Implemented

### 2026-03-13: Initial Setup & Deployment
- ✅ Клоновано репозиторій з GitHub
- ✅ Налаштовано backend (FastAPI) на порту 8001
- ✅ Налаштовано frontend (React) на порту 3000
- ✅ MongoDB підключено та працює
- ✅ BOT_TOKEN налаштований
- ✅ Тестові сигнали завантажені (15 шт)

### Geo Intel Module Features
- ✅ **Map API** - `/api/geo/map` повертає сигнали
- ✅ **Heatmap** - `/api/geo/heatmap` для теплової карти
- ✅ **Signal Reports** - створення та голосування за сигнали
- ✅ **User Profiles** - профілі з XP та рівнями
- ✅ **Privacy Settings** - налаштування збереження локації

### MiniApp Features
- ✅ **RadarPage** - карта з сигналами (Leaflet)
- ✅ **ReportPage** - вибір типу сигналу з іконками
- ✅ **AlertsPage** - список алертів
- ✅ **ProfilePage** - профіль, рейтинг, налаштування
- ✅ **BottomNav** - навігація з 4 табами

---

## API Endpoints

### Geo/Map
- `GET /api/geo/health` - Health check
- `GET /api/geo/map?days=7&limit=50` - Сигнали для карти
- `GET /api/geo/radar?lat=&lng=&radius=` - Nearby signals
- `GET /api/geo/heatmap` - Heatmap data
- `GET /api/geo/top` - Top places

### MiniApp
- `POST /api/geo/miniapp/report` - Створення сигналу (JSON)
- `POST /api/geo/miniapp/report-with-photo` - Створення з фото (multipart)
- `POST /api/geo/miniapp/signal/{id}/vote` - Голосування
- `GET /api/geo/miniapp/user/{id}/profile` - Профіль користувача
- `GET /api/geo/miniapp/user/{id}/settings` - Privacy налаштування
- `POST /api/geo/miniapp/user/{id}/settings` - Оновлення налаштувань
- `GET /api/geo/miniapp/user/{id}/alerts` - Alerts користувача
- `GET /api/geo/miniapp/channel/check` - Перевірка підписки на канал

---

## Signal Types
| ID | Emoji | Title | Priority |
|----|-------|-------|----------|
| danger | 🚨 | НЕБЕЗПЕКА | high |
| police | 🚔 | ПОЛІЦІЯ | medium |
| incident | ⚠️ | ІНЦИДЕНТ | medium |
| weather | 🌧️ | ПОГОДА | low |
| virus | ☣️ | БІОЗАГРОЗА | high |
| trash | 🗑️ | СМІТТЯ | low |
| fire | 🔥 | ПОЖЕЖА | critical |
| accident | 💥 | ДТП | high |
| flood | 🌊 | ПІДТОПЛЕННЯ | medium |
| road_works | 🚧 | ДОРОЖНІ РОБОТИ | low |

---

## File Structure
```
/app/
├── backend/
│   ├── server.py                 # Main FastAPI app
│   ├── .env                      # BOT_TOKEN, CHANNEL_ID, MONGO_URL
│   └── geo_intel/
│       ├── router.py             # All geo endpoints
│       └── services/
│           ├── channel_publisher.py
│           ├── aggregator.py
│           ├── proximity.py
│           └── ...
├── frontend/
│   ├── .env                      # REACT_APP_BACKEND_URL
│   └── src/miniapp/
│       ├── MiniApp.jsx           # Main app component
│       ├── MiniApp.css           # All styles
│       ├── pages/
│       │   ├── RadarPage.jsx
│       │   ├── ReportPage.jsx
│       │   ├── AlertsPage.jsx
│       │   └── ProfilePage.jsx
│       ├── components/
│       │   ├── BottomNav.jsx
│       │   └── MapPickerModal.jsx
│       ├── stores/
│       │   └── appStore.js       # Zustand store
│       └── lib/
│           ├── telegram.js
│           └── signalTypes.js
└── memory/
    └── PRD.md
```

---

## Prioritized Backlog

### P0 (Critical) - DONE ✅
- [x] Project deployment
- [x] Backend API working
- [x] Frontend MiniApp working
- [x] Map with signals
- [x] Navigation working

### P1 (High Priority) - TODO
- [ ] MTProto String Session integration (user requested for later)
- [ ] Event Builder + Correlation Layer (описано в problem statement)
- [ ] Dedup Engine для об'єднання сигналів
- [ ] Signal Decay logic
- [ ] Real-time alerts через бот

### P2 (Medium Priority)
- [ ] Confidence formula improvement
- [ ] Multi-location сообщения
- [ ] Source weighting
- [ ] Photo verification bonus

### P3 (Future)
- [ ] AI Signal Classification з OpenAI
- [ ] Pattern detection
- [ ] Safe route planning
- [ ] Premium subscriptions

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

## Testing Results (2026-03-13)
- Backend: 100% tests passed
- Frontend: 95% tests passed
- All core functionality working

---

*Last updated: 2026-03-13*
