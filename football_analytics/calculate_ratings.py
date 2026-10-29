import requests
import pandas as pd

API_KEY = "53eda6d8b3e840f3b4253486531061bf"
HEADERS = {"X-Auth-Token": API_KEY}
LEAGUE_CODE = "PL"

# 1. Fetch finished match results
url = f"https://api.football-data.org/v4/competitions/{LEAGUE_CODE}/matches?status=FINISHED"
response = requests.get(url, headers=HEADERS)
data = response.json()
matches = data.get("matches", [])

records = []
for m in matches:
    score = m.get("score", {}).get("fullTime", {})
    h_goals = score.get("home")
    a_goals = score.get("away")
    if h_goals is not None and a_goals is not None:
        records.append({
            "home_team": m.get("homeTeam", {}).get("name"),
            "away_team": m.get("awayTeam", {}).get("name"),
            "home_goals": int(h_goals),
            "away_goals": int(a_goals)
        })

df = pd.DataFrame(records)

# 2. League-wide baseline scoring rates
total_matches = len(df)
avg_home_goals = df["home_goals"].mean()
avg_away_goals = df["away_goals"].mean()

print(f"Total Matches Analyzed: {total_matches}")
print(f"League Avg Home Goals: {avg_home_goals:.3f}")
print(f"League Avg Away Goals: {avg_away_goals:.3f}\n")

# 3. Aggregate performance by team
home_stats = df.groupby("home_team").agg(
    home_games=("home_goals", "count"),
    home_goals_scored=("home_goals", "sum"),
    home_goals_conceded=("away_goals", "sum")
).reset_index().rename(columns={"home_team": "team"})

away_stats = df.groupby("away_team").agg(
    away_games=("away_goals", "count"),
    away_goals_scored=("away_goals", "sum"),
    away_goals_conceded=("home_goals", "sum")
).reset_index().rename(columns={"away_team": "team"})

# Merge stats
teams_df = pd.merge(home_stats, away_stats, on="team", how="outer").fillna(0)

# Calculate Per-Match Averages
teams_df["avg_home_scored"] = teams_df["home_goals_scored"] / teams_df["home_games"]
teams_df["avg_home_conceded"] = teams_df["home_goals_conceded"] / teams_df["home_games"]
teams_df["avg_away_scored"] = teams_df["away_goals_scored"] / teams_df["away_games"]
teams_df["avg_away_conceded"] = teams_df["away_goals_conceded"] / teams_df["away_games"]

# 4. Attack & Defense Coefficients relative to the league average
teams_df["home_attack"] = (teams_df["avg_home_scored"] / avg_home_goals).round(3)
teams_df["home_defense"] = (teams_df["avg_home_conceded"] / avg_away_goals).round(3)
teams_df["away_attack"] = (teams_df["avg_away_scored"] / avg_away_goals).round(3)
teams_df["away_defense"] = (teams_df["avg_away_conceded"] / avg_home_goals).round(3)

# Display summary table sorted by strongest home attack
output_cols = ["team", "home_attack", "home_defense", "away_attack", "away_defense"]
ratings_table = teams_df[output_cols].sort_values(by="home_attack", ascending=False)

print("--- TEAM ATTACK & DEFENSE RATINGS ---")
print(ratings_table.to_string(index=False))