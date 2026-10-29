import requests
import pandas as pd

API_KEY = "53eda6d8b3e840f3b4253486531061bf"
HEADERS = {"X-Auth-Token": API_KEY}

# Supported competition codes:
# 'PL' (Premier League), 'PD' (La Liga), 'SA' (Serie A), 'BL1' (Bundesliga), 'FL1' (Ligue 1), 'CL' (Champions League)
LEAGUE_CODE = "PL"

url = f"https://api.football-data.org/v4/competitions/{LEAGUE_CODE}/matches?status=FINISHED"

print(f"Fetching finished matches for {LEAGUE_CODE}...")
response = requests.get(url, headers=HEADERS)

if response.status_code == 200:
    data = response.json()
    matches = data.get("matches", [])
    
    records = []
    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        records.append({
            "matchday": m.get("matchday"),
            "home_team": m.get("homeTeam", {}).get("name"),
            "away_team": m.get("awayTeam", {}).get("name"),
            "home_score": score.get("home"),
            "away_score": score.get("away"),
        })

    df = pd.DataFrame(records)
    
    print("\n--- DATA EXTRACTION SUCCESSFUL ---")
    print(f"Total Matches Pulled: {len(df)}")
    print("\nRecent 5 Matches:")
    print(df.tail(5).to_string(index=False))
else:
    print(f"Error {response.status_code}: {response.text}")