import numpy as np
import pandas as pd
from scipy.stats import poisson
import requests

API_KEY = "53eda6d8b3e840f3b4253486531061bf"
HEADERS = {"X-Auth-Token": API_KEY}
LEAGUE_CODE = "PL"

# 1. Pull latest match data
url = f"https://api.football-data.org/v4/competitions/{LEAGUE_CODE}/matches?status=FINISHED"
response = requests.get(url, headers=HEADERS)
matches = response.json().get("matches", [])

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
avg_home_goals = df["home_goals"].mean()
avg_away_goals = df["away_goals"].mean()

# 2. Build Team Ratings
home_stats = df.groupby("home_team").agg(
    home_games=("home_goals", "count"),
    home_scored=("home_goals", "sum"),
    home_conceded=("away_goals", "sum")
).reset_index().rename(columns={"home_team": "team"})

away_stats = df.groupby("away_team").agg(
    away_games=("away_goals", "count"),
    away_scored=("away_goals", "sum"),
    away_conceded=("home_goals", "sum")
).reset_index().rename(columns={"away_team": "team"})

stats = pd.merge(home_stats, away_stats, on="team", how="outer").fillna(0)

stats["home_attack"] = (stats["home_scored"] / stats["home_games"]) / avg_home_goals
stats["home_defense"] = (stats["home_conceded"] / stats["home_games"]) / avg_away_goals
stats["away_attack"] = (stats["away_scored"] / stats["away_games"]) / avg_away_goals
stats["away_defense"] = (stats["away_conceded"] / stats["away_games"]) / avg_home_goals

ratings = stats.set_index("team")

# 3. Simulation Function
def calculate_fixture(home_team, away_team):
    if home_team not in ratings.index or away_team not in ratings.index:
        print(f"Error: Either '{home_team}' or '{away_team}' was not found in the dataset.")
        return

    # Expected goals for each team
    h_att = ratings.loc[home_team, "home_attack"]
    a_def = ratings.loc[away_team, "away_defense"]
    a_att = ratings.loc[away_team, "away_attack"]
    h_def = ratings.loc[home_team, "home_defense"]

    lambda_home = h_att * a_def * avg_home_goals
    mu_away = a_att * h_def * avg_away_goals

    # 6x6 score probability matrix (0 to 5 goals)
    max_goals = 6
    h_probs = [poisson.pmf(i, lambda_home) for i in range(max_goals)]
    a_probs = [poisson.pmf(j, mu_away) for j in range(max_goals)]
    grid = np.outer(h_probs, a_probs)

    # Market probabilities
    p_home_win = float(np.sum(np.tril(grid, -1)))
    p_draw = float(np.sum(np.diag(grid)))
    p_away_win = float(np.sum(np.triu(grid, 1)))

    p_over_25 = float(sum(grid[i][j] for i in range(max_goals) for j in range(max_goals) if i + j > 2.5))
    p_under_25 = 1.0 - p_over_25
    p_btts = float(sum(grid[i][j] for i in range(1, max_goals) for j in range(1, max_goals)))

    print("=" * 55)
    print(f"MATCH: {home_team} vs {away_team}")
    print(f"Expected Goals (xG) -> {home_team}: {lambda_home:.2f} | {away_team}: {mu_away:.2f}")
    print("=" * 55)
    print(f"{'Market / Outcome':<25} | {'Probability':<12} | {'Fair Odds'}")
    print("-" * 55)
    print(f"{home_team + ' Win (1)':<25} | {p_home_win * 100:>10.2f}% | {1 / p_home_win:>8.2f}")
    print(f"{'Draw (X)':<25} | {p_draw * 100:>10.2f}% | {1 / p_draw:>8.2f}")
    print(f"{away_team + ' Win (2)':<25} | {p_away_win * 100:>10.2f}% | {1 / p_away_win:>8.2f}")
    print("-" * 55)
    print(f"{'Over 2.5 Goals':<25} | {p_over_25 * 100:>10.2f}% | {1 / p_over_25:>8.2f}")
    print(f"{'Under 2.5 Goals':<25} | {p_under_25 * 100:>10.2f}% | {1 / p_under_25:>8.2f}")
    print(f"{'Both Teams To Score (Yes)':<25} | {p_btts * 100:>10.2f}% | {1 / p_btts:>8.2f}")
    print("=" * 55)

# Example run: Pick two teams from your previous table
calculate_fixture("Arsenal FC", "Chelsea FC")