# Stylist — Deep Winter AI Shopping Agent

A personal AI shopping agent that scrapes ASOS and Nordstrom, analyzes products against your **Deep Winter** seasonal color profile, and surfaces curated matches in a clean dashboard.

---

## Architecture

```
stylist/
├── backend/          # Python / FastAPI
│   ├── app/
│   │   ├── main.py               # FastAPI app + APScheduler
│   │   ├── config.py             # All settings (env-driven)
│   │   ├── database.py           # SQLAlchemy async engine
│   │   ├── models/               # SQLAlchemy ORM models
│   │   │   ├── product.py
│   │   │   ├── match.py
│   │   │   ├── user_feedback.py
│   │   │   └── alert.py
│   │   ├── schemas/              # Pydantic response schemas
│   │   ├── routers/              # FastAPI route handlers
│   │   │   ├── matches.py        # GET /api/v1/matches/
│   │   │   ├── products.py       # GET /api/v1/products/
│   │   │   ├── feedback.py       # POST /api/v1/feedback/{match_id}
│   │   │   ├── alerts.py         # GET /api/v1/alerts/
│   │   │   └── scraper.py        # POST /api/v1/scraper/run
│   │   ├── scrapers/
│   │   │   ├── base.py           # Playwright base class
│   │   │   ├── asos.py           # ASOS scraper (JSON API + detail pages)
│   │   │   └── nordstrom.py      # Nordstrom scraper
│   │   ├── analysis/
│   │   │   ├── color_matcher.py  # Google Vision + Delta-E 2000
│   │   │   ├── fabric_parser.py  # Regex + NLP fiber extraction
│   │   │   └── claude_analyzer.py # Claude API style analysis
│   │   └── scheduler/
│   │       └── jobs.py           # Daily pipeline orchestrator
│   ├── alembic/                  # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/         # React / TypeScript / Tailwind
    ├── src/
    │   ├── App.tsx
    │   ├── lib/api.ts            # Axios client + TypeScript types
    │   ├── hooks/useMatches.ts   # React Query hooks
    │   ├── components/
    │   │   ├── ProductCard.tsx   # Match card with accept/reject
    │   │   ├── FilterSidebar.tsx # Score, brand, price filters
    │   │   └── ColorSwatches.tsx # Dominant color display
    │   └── pages/
    │       ├── Dashboard.tsx     # Daily matches grid
    │       ├── Wishlist.tsx      # Saved / accepted items
    │       └── Alerts.tsx        # Price drops & restocks
    └── Dockerfile
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12+ |
| Node.js | 20+ |
| Docker + Docker Compose | latest |
| PostgreSQL | 16 (via Docker) |
| Redis | 7 (via Docker) |

---

## Quick Start (Docker)

### 1. Clone and configure

```bash
git clone <repo-url>
cd stylist
cp .env.example backend/.env
```

Edit `backend/.env` and add your API keys:

```env
GOOGLE_VISION_API_KEY=your_key_here
ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Start all services

```bash
docker-compose up --build
```

This starts:
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`
- FastAPI backend on `http://localhost:8000`
- React frontend on `http://localhost:5173`

### 3. Run your first scrape

Either wait for the daily 06:00 UTC job, or trigger manually:

```bash
curl -X POST http://localhost:8000/api/v1/scraper/run
```

Or click **Scan now** in the dashboard.

---

## Local Development (without Docker)

### Backend

```bash
cd backend

# Create virtualenv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Copy env file
cp .env.example .env
# Edit .env with your values

# Start local PostgreSQL + Redis (or use Docker for just these):
docker-compose up db redis -d

# Run database migrations
alembic upgrade head

# Start the API
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/matches/` | List matches (filterable) |
| GET | `/api/v1/matches/{id}` | Single match detail |
| PATCH | `/api/v1/matches/{id}/read` | Mark as read |
| POST | `/api/v1/feedback/{match_id}` | Accept / reject / save |
| GET | `/api/v1/feedback/wishlist` | Saved items |
| GET | `/api/v1/alerts/` | Price drop alerts |
| PATCH | `/api/v1/alerts/{id}/read` | Mark alert read |
| PATCH | `/api/v1/alerts/read-all` | Mark all alerts read |
| POST | `/api/v1/scraper/run` | Trigger scrape (background) |
| GET | `/health` | Health check |

Interactive docs available at `http://localhost:8000/docs`.

### Match filter parameters

```
GET /api/v1/matches/?min_score=70&brand=Sézane&price_max=300&is_new=true
```

| Param | Default | Description |
|-------|---------|-------------|
| `min_score` | 70 | Minimum overall match score (0–100) |
| `brand` | — | Filter by brand name (partial match) |
| `price_min` | — | Minimum price |
| `price_max` | — | Maximum price |
| `is_new` | — | Only show items from today's scrape |
| `page` | 1 | Page number |
| `page_size` | 24 | Items per page |

---

## How the Matching Pipeline Works

```
Scraper (Playwright)
      │
      ▼
Product data extracted
  • name, brand, price, color_name
  • image_url
  • fabric_raw (from detail page)
      │
      ▼
Fabric Parser (regex + NLP)
  • Extracts fiber percentages: "80% Silk, 20% Cotton"
  • Scores 0–100 (silk=100, linen=85, cotton=75, polyester=FAIL)
  • Hard-excludes polyester, acrylic, "satin" without silk
      │
      │  if fabric passes →
      ▼
Color Matcher (Google Vision API + Delta-E 2000)
  • Sends image to Vision API → dominant colors [{hex, %}]
  • Computes ΔE 2000 from each dominant color to every
    Deep Winter palette color
  • Converts ΔE to 0–100 confidence score
  • Applies warm-tone veto (excludes camel, peach, mustard range)
      │
      │  if score ≥ 70 →
      ▼
Claude Analysis (claude-sonnet-4-6)
  • Explains WHY item works for Deep Winter coloring
  • Flags borderline matches with nuanced reasoning
  • Parses ambiguous fabric descriptions
      │
      ▼
Match record created in DB
  • Composite score = 60% color + 30% fabric + 10% brand priority
      │
      ▼
Dashboard (React)
  • Grid of matches with color swatches, scores, Claude analysis
  • Accept / reject / save buttons
  • Price drop alerts
```

---

## Deep Winter Color Profile

**Best colors** (what we score for):

| Color | Hex |
|-------|-----|
| Black | `#000000` |
| Bright White | `#FFFFFF` |
| Emerald | `#006B3C` |
| Royal Blue | `#4169E1` |
| True Red | `#CC0000` |
| Burgundy | `#800020` |
| Deep Plum | `#580F41` |
| Fuchsia | `#FF0090` |
| Cobalt | `#0047AB` |
| Charcoal | `#36454F` |
| Navy | `#000080` |
| Teal | `#008080` |
| Mahogany | `#3C1F1F` |

**Excluded warm tones**: camel, tan, beige, ivory, cream, mustard, warm yellow, peach, coral, orange, warm terracotta, warm olive green.

---

## API Keys Required

### Google Vision API
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **Cloud Vision API**
3. Create an API key under Credentials
4. Add to `backend/.env` as `GOOGLE_VISION_API_KEY`

**Without this key**: the app still works but color scores will be 0 (no vision analysis). Claude will still analyze color names from the retailer listing.

### Anthropic API
1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Create an API key
3. Add to `backend/.env` as `ANTHROPIC_API_KEY`

**Without this key**: matches still surface (color + fabric scoring works), but the "Stylist analysis" section on each card will be empty.

---

## Deployment (Railway)

```bash
# Install Railway CLI
npm install -g @railway/cli

railway login
railway init

# Add environment variables
railway variables set GOOGLE_VISION_API_KEY=...
railway variables set ANTHROPIC_API_KEY=...

# Deploy
railway up
```

Railway auto-detects the `docker-compose.yml` for multi-service deployments.

---

## Phase 2 Roadmap

- [ ] Add more retailers: Net-a-Porter, Shopbop, Farfetch
- [ ] Size/availability tracking with restock alerts
- [ ] Email digest of weekly top matches
- [ ] Browser extension for one-click analysis on any product page
- [ ] Fine-tune color scoring weights based on accepted/rejected feedback
- [ ] Multi-user support with per-user color profiles
