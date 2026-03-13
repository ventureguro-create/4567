# Telegram MiniApp Geo-Radar PRD

## Project Overview
Telegram MiniApp для моніторингу та звітування про події в місті в реальному часі. Privacy-first підхід з автоматичним видаленням даних.

**Repository:** https://github.com/ventureguro-create/56789
**Preview URL:** https://ea157ab2-3502-4b8d-9e89-ea2a8d089bcf.preview.emergentagent.com

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

### 2026-03-12: Initial Setup
- ✅ Клоновано репозиторій, розгорнуто проект
- ✅ **Layout Fix** - виправлено перекриття елементів:
  - `.bottom-nav-modern`: `bottom: 0`
  - `.radar-bottom-panel`: `bottom: 80px`
  - `.nearby-signals-panel`: `bottom: 150px`

### 2026-03-12: Map Markers
- ✅ Прибрано glow ефект з іконок - чисті PNG
- ✅ Збільшено розміри маркерів: 28→36→44→52px (zoom scaling)
- ✅ Додано контрастну тінь `drop-shadow(0 2px 3px rgba(0,0,0,0.35))`
- ✅ Вимкнено heatmap для чистої карти

### 2026-03-13: Channel Integration
- ✅ **Кнопка "Телеграм-канал"** в Profile
- ✅ Перевірка підписки через Bot API `getChatMember`
- ✅ Badge "Підписано" / "Підписатись"

### 2026-03-13: Auto-posting to Channel
- ✅ **ChannelPublisher** сервіс (`/backend/geo_intel/services/channel_publisher.py`)
- ✅ Красиве форматування постів з emoji та пріоритетами
- ✅ Автоматична публікація при створенні сигналу
- ✅ Підтримка фото в постах (`sendPhoto` API)

**Формат поста:**
```
🚔 ПОЛІЦІЯ 🟡
📍 Локація: Центр
🕐 Час: 13:50
💬 Опис...
━━━━━━━━━━━━━━━
⚡ Дотримуйтесь ПДР
🗺️ Переглянути на карті
#radar #police #Центр
```

### 2026-03-13: Photo Upload + Privacy
- ✅ **Новий ReportPage** з flow: Тип → Локація + Фото + Опис
- ✅ Камера через `<input capture="environment">`
- ✅ Preview фото з Retake/Remove
- ✅ Endpoint `/api/geo/miniapp/report-with-photo` (multipart)
- ✅ **Privacy налаштування:**
  - Зберігання геолокації: Ні / 15хв / 1год / 24год
  - Точність локації: Точна / Приблизна (±100м)
- ✅ API: GET/POST `/api/geo/miniapp/user/{id}/settings`

### 2026-03-13: Route Avoidance
- ✅ **Кнопки обходу маршруту** в SignalCard:
  - 🔵 "Обійти пішки" → Google Maps walking
  - 🟣 "Об'їхати" → Google Maps driving
- ✅ Тестові сигнали (13 шт) біля центру Києва

---

## API Endpoints

### Geo/Map
- `GET /api/geo/health` - Health check
- `GET /api/geo/map?days=7&limit=50` - Сигнали для карти
- `GET /api/geo/radar?lat=&lng=&radius=` - Nearby signals

### MiniApp
- `POST /api/geo/miniapp/report` - Створення сигналу (JSON)
- `POST /api/geo/miniapp/report-with-photo` - Створення з фото (multipart)
- `POST /api/geo/miniapp/signal/{id}/vote` - Голосування
- `GET /api/geo/miniapp/user/{id}/profile` - Профіль користувача
- `GET /api/geo/miniapp/user/{id}/settings` - Privacy налаштування
- `POST /api/geo/miniapp/user/{id}/settings` - Оновлення налаштувань
- `GET /api/geo/miniapp/user/{id}/alerts` - Alerts користувача
- `GET /api/geo/miniapp/channel/check` - Перевірка підписки на канал
- `GET /api/geo/miniapp/channel/preview-post` - Preview формату поста
- `GET /api/geo/miniapp/subscription/status` - Статус підписки
- `POST /api/geo/miniapp/subscription/create-invoice` - Stars invoice

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
│           ├── channel_publisher.py  # Auto-posting to channel
│           ├── aggregator.py
│           ├── proximity.py
│           └── ...
├── frontend/
│   ├── .env                      # REACT_APP_BACKEND_URL
│   └── src/miniapp/
│       ├── MiniApp.jsx           # Main app component
│       ├── MiniApp.css           # All styles
│       ├── pages/
│       │   ├── RadarPage.jsx     # Map + signals + route avoidance
│       │   ├── ReportPage.jsx    # Signal creation with photo
│       │   ├── AlertsPage.jsx    # User alerts
│       │   └── ProfilePage.jsx   # Profile + settings + privacy
│       ├── components/
│       │   ├── BottomNav.jsx
│       │   └── MapPickerModal.jsx
│       ├── stores/
│       │   └── appStore.js       # Zustand store
│       └── lib/
│           ├── telegram.js       # Telegram WebApp utils
│           └── signalTypes.js    # Signal type configs
└── memory/
    └── PRD.md                    # This file
```

---

## Prioritized Backlog

### P0 (Critical) - DONE ✅
- [x] Layout fixes
- [x] Map markers visibility
- [x] Channel auto-posting
- [x] Photo upload
- [x] Privacy settings
- [x] Route avoidance buttons

### P1 (High Priority) - TODO
- [ ] MTProto String Session integration
- [ ] Real signal data from Telegram channels (ingestion)
- [ ] Signal decay logic (auto-expire)
- [ ] Cron для автоматичного видалення старих даних
- [ ] Push notifications через бот

### P2 (Medium Priority)
- [ ] User authentication via Telegram WebApp
- [ ] Reward system (XP, levels, badges)
- [ ] Leaderboard з реальними даними
- [ ] Summary posts (зведення за годину/день)

### P3 (Future)
- [ ] Heatmap optimization
- [ ] Route safety analysis (avoid all signals on route)
- [ ] Premium subscriptions via Telegram Stars
- [ ] Multi-city support

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
REACT_APP_BACKEND_URL=https://ea157ab2-3502-4b8d-9e89-ea2a8d089bcf.preview.emergentagent.com
```

---

## Testing Notes
- Тестові сигнали: 13 шт біля центру Києва (50.4501, 30.5234)
- Бот доданий як адмін каналу @ARKHOR
- Автопостинг працює з фото та без

---

*Last updated: 2026-03-13*
