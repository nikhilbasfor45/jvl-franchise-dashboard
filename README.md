# JVL Franchise Owner Dashboard

A production-ready Streamlit web app for franchise owners to explore startups, rate them, shortlist them, and review performance analytics.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Default Users

- admin / admin123 (role: admin)
- owner / owner123 (role: franchise_owner)

You can change these later by editing the users table in SQLite.

## Features

- Upload and normalize startup data from Excel
- Search, filter, and view startup details
- Rate startups with comments
- Shortlist startups and export to CSV
- Leaderboard and analytics
- Admin exports for ratings, shortlists, and master startup data

## File Structure

```
jvl-franchise-dashboard/
  app.py
  requirements.txt
  README.md
  /data
  /db
  /src
  /assets
```
