# Places Data

This directory is reserved for local POI datasets used by TravelAgent.

Current demo seed data lives in `backend/agents/travel/seed_data.py` so it can be imported without a loading pipeline. As the dataset grows, move city packs here, for example:

- `china/hangzhou.json`
- `china/beijing.json`
- `china/shanghai.json`
- `global/tokyo.json`

The intended model is: curated local POI data first, Tencent Map fallback second, runtime cache third.