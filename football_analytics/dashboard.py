import streamlit as st
import numpy as np
import pandas as pd
from scipy.stats import poisson
import requests
from datetime import datetime, timezone

st.set_page_config(page_title="Football Quant & Match Operations Center", layout="wide")

API_KEY = "53eda6d8b3e840f3b4253486531061bf"
HEADERS = {"X-Auth-Token": API_KEY}

LEAGUES = {
    "Premier League": "PL",
    "La Liga (Spain)": "PD",
    "Serie A (Italy)": "SA",
    "Bundesliga (Germany)": "BL1",
    "Ligue 1 (France)": "FL1",
    "UEFA Champions League": "CL"
}

CSV_LEAGUE_MAP = {
    "PL": "E0",
    "PD": "SP1",
    "SA": "I1",
    "BL1": "D1",
    "FL1": "F1"
}

POWER_INDEX = {
    # Premier League
    "Manchester City FC": 1950, "Arsenal FC": 1920, "Liverpool FC": 1910, "Chelsea FC": 1790,
    "Newcastle United FC": 1770, "Tottenham Hotspur FC": 1780, "Manchester United FC": 1740,
    "Aston Villa FC": 1770, "Brighton & Hove Albion FC": 1730, "Brentford FC": 1660,
    "Fulham FC": 1640, "AFC Bournemouth": 1640, "Crystal Palace FC": 1630, "West Ham United FC": 1650,
    "Everton FC": 1610, "Wolverhampton Wanderers FC": 1610, "Nottingham Forest FC": 1620,
    "Leicester City FC": 1570, "Ipswich Town FC": 1530, "Southampton FC": 1520,
    
    # Serie A
    "SSC Napoli": 1820, "FC Internazionale Milano": 1880, "Juventus FC": 1810, "AC Milan": 1800,
    "Atalanta BC": 1790, "SS Lazio": 1740, "AS Roma": 1740, "AC Monza": 1560, "Empoli FC": 1540,
    "Venezia FC": 1490, "Parma Calcio 1913": 1520, "Como 1907": 1510, "Cagliari Calcio": 1520,
    "Hellas Verona FC": 1530, "US Lecce": 1510, "Udinese Calcio": 1580, "Torino FC": 1640,
    "Bologna FC 1909": 1680, "ACF Fiorentina": 1720, "Genoa CFC": 1570,
    
    # La Liga
    "Real Madrid CF": 1960, "FC Barcelona": 1930, "Club Atlético de Madrid": 1820,
    "Athletic Club": 1760, "Real Sociedad de Fútbol": 1740, "Real Betis Balompié": 1720,
    "Villarreal CF": 1730, "Girona FC": 1710, "Sevilla FC": 1680, "Valencia CF": 1640,
    "RC Celta de Vigo": 1630, "CA Osasuna": 1640, "RCD Mallorca": 1620, "Getafe CF": 1610,

    # Bundesliga
    "FC Bayern München": 1930, "Bayer 04 Leverkusen": 1870, "Borussia Dortmund": 1820,
    "RB Leipzig": 1810, "Eintracht Frankfurt": 1730, "VfB Stuttgart": 1740, "Sport-Club Freiburg": 1680,

    # Ligue 1
    "Paris Saint-Germain FC": 1890, "AS Monaco FC": 1770, "Olympique de Marseille": 1750,
    "Lille OSC": 1740, "Olympique Lyonnais": 1710, "OGC Nice": 1690, "Stade Rennais FC 1904": 1670
}

# Generic fuzzy Elo mapper for historical CSV team naming variants
def get_historical_elo(team_name):
    clean = str(team_name).lower().replace("fc", "").replace("afc", "").replace("cf", "").strip()
    for full_name, elo in POWER_INDEX.items():
        base = full_name.lower().replace("fc", "").replace("afc", "").replace("cf", "").strip()
        if clean in base or base in clean:
            return elo
    return 1550

if "app_view" not in st.session_state:
    st.session_state.app_view = "📅 Fixtures & League Monitor"
if "selected_home" not in st.session_state:
    st.session_state.selected_home = None
if "selected_away" not in st.session_state:
    st.session_state.selected_away = None
if "target_match_date" not in st.session_state:
    st.session_state.target_match_date = datetime.now(timezone.utc)

st.sidebar.title("Navigation & Parameters")
views_list = [
    "📅 Fixtures & League Monitor",
    "⚡ Quant Odds Simulator",
    "📈 Model Accuracy & Evaluation",
    "🎯 5-Year Market Benchmark & Top 2 Selection"
]

def sync_view():
    st.session_state.app_view = st.session_state.sidebar_nav

selected_nav = st.sidebar.radio(
    "Go To",
    views_list,
    index=views_list.index(st.session_state.app_view),
    key="sidebar_nav",
    on_change=sync_view
)
st.sidebar.divider()

selected_league_label = st.sidebar.selectbox("Select Competition", list(LEAGUES.keys()))
league_code = LEAGUES[selected_league_label]

st.sidebar.subheader("Dataset Depth Tuning")
lookback_window = st.sidebar.slider("Rolling Matches Lookback Per Team", min_value=5, max_value=30, value=20, step=1)
decay_factor = st.sidebar.slider("Recency Weight Decay", min_value=0.0, max_value=0.15, value=0.03, step=0.01)

# --- LIVE API DATA FETCHERS ---
@st.cache_data(ttl=600)
def fetch_league_standings(code):
    url = f"https://api.football-data.org/v4/competitions/{code}/standings"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    tables = resp.json().get("standings", [])
    return tables[0].get("table", []) if tables else []

@st.cache_data(ttl=600)
def fetch_scheduled_fixtures(code):
    url = f"https://api.football-data.org/v4/competitions/{code}/matches?status=SCHEDULED,TIMED"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    return resp.json().get("matches", [])

@st.cache_data(ttl=1200)
def fetch_cross_competition_matches(primary_code):
    codes_to_fetch = list(set([primary_code, "CL", "PL", "PD", "SA", "BL1", "FL1"]))
    all_records = []
    
    for c in codes_to_fetch:
        url = f"https://api.football-data.org/v4/competitions/{c}/matches?status=FINISHED"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            for m in resp.json().get("matches", []):
                score = m.get("score", {}).get("fullTime", {})
                h_g = score.get("home")
                a_g = score.get("away")
                utc_dt = m.get("utcDate")
                if h_g is not None and a_g is not None and utc_dt:
                    dt_obj = pd.to_datetime(utc_dt)
                    if dt_obj.tzinfo is None:
                        dt_obj = dt_obj.tz_localize(timezone.utc)
                    else:
                        dt_obj = dt_obj.tz_convert(timezone.utc)
                    all_records.append({
                        "match_id": m.get("id"),
                        "comp": c,
                        "home_team": m.get("homeTeam", {}).get("name"),
                        "away_team": m.get("awayTeam", {}).get("name"),
                        "match_date": dt_obj,
                        "home_goals": int(h_g),
                        "away_goals": int(a_g)
                    })
    df = pd.DataFrame(all_records).drop_duplicates(subset=["match_id"])
    return df.sort_values("match_date").reset_index(drop=True)

cross_comp_df = fetch_cross_competition_matches(league_code)
finished_df = cross_comp_df[cross_comp_df["comp"] == league_code].copy() if not cross_comp_df.empty else pd.DataFrame()
standings_data = fetch_league_standings(league_code)
scheduled_data = fetch_scheduled_fixtures(league_code)

def compute_ratings(df_finished, lookback=20, decay=0.03):
    if df_finished.empty:
        return None, 1.45, 1.15
    
    facts = []
    for _, r in df_finished.iterrows():
        hg = int(r["home_goals"])
        ag = int(r["away_goals"])
        dt = r["match_date"]
        
        hsot = hg + 3
        asot = ag + 2
        hxg = round(hsot * 0.32 + 0.15, 2)
        axg = round(asot * 0.30 + 0.12, 2)

        facts.append({"team": r["home_team"], "match_date": dt, "venue": "Home", "xg": hxg, "xga": axg})
        facts.append({"team": r["away_team"], "match_date": dt, "venue": "Away", "xg": axg, "xga": hxg})

    f_df = pd.DataFrame(facts)
    max_d = f_df["match_date"].max()
    f_df["days_ago"] = (max_d - f_df["match_date"]).dt.total_seconds() / (24 * 3600)
    f_df["weight"] = np.exp(-decay * (f_df["days_ago"] / 7.0))

    teams = sorted(f_df["team"].unique())
    sel_idx = []
    games_count_dict = {}

    for t in teams:
        t_games = f_df[f_df["team"] == t].tail(lookback)
        sel_idx.extend(t_games.index)
        games_count_dict[t] = len(t_games)
    
    roll = f_df.loc[sorted(list(set(sel_idx)))].copy()
    w_tot = roll["weight"].sum()
    avg_xg = (roll["xg"] * roll["weight"]).sum() / w_tot
    avg_xga = (roll["xga"] * roll["weight"]).sum() / w_tot

    team_stats = []
    for t in teams:
        grp = roll[roll["team"] == t]
        if grp.empty:
            continue
        w = grp["weight"].sum()
        txg = (grp["xg"] * grp["weight"]).sum() / w
        txga = (grp["xga"] * grp["weight"]).sum() / w
        
        prior_k = 4.0
        shrunk_att = (txg * w + prior_k * avg_xg) / (w + prior_k)
        shrunk_def = (txga * w + prior_k * avg_xga) / (w + prior_k)

        team_stats.append({
            "team": t,
            "sample_size": games_count_dict.get(t, len(grp)),
            "att": shrunk_att / max(avg_xg, 0.1),
            "def": shrunk_def / max(avg_xga, 0.1),
            "avg_xg": round(txg, 2),
            "avg_xga": round(txga, 2)
        })
    return pd.DataFrame(team_stats).set_index("team"), avg_xg, avg_xga

ratings_df, league_avg_xg, league_avg_xga = compute_ratings(finished_df, lookback=lookback_window, decay=decay_factor)

def compute_context_modifier(rest_days, absences, congestion, rotations):
    rest_factor = 1.0 - (0.05 * max(0, 3 - rest_days))
    cong_factor = 0.94 if congestion else 1.0
    abs_factor = 1.0 - (0.07 * absences)
    rot_factor = 1.0 - (0.02 * max(0, rotations - 2))
    return float(max(rest_factor * cong_factor * abs_factor * rot_factor, 0.60))

@st.cache_data(ttl=86400)
def fetch_five_year_historical_dataset(div_code):
    seasons = ["2021", "2122", "2223", "2324", "2425"]
    dfs = []
    for s in seasons:
        csv_url = f"https://www.football-data.co.uk/mmz4281/{s}/{div_code}.csv"
        try:
            temp_df = pd.read_csv(csv_url, encoding="latin1")
            temp_df = temp_df[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].dropna()
            temp_df["Season"] = s
            dfs.append(temp_df)
        except Exception:
            continue
    if dfs:
        full_df = pd.concat(dfs, ignore_index=True)
        full_df["FTHG"] = full_df["FTHG"].astype(int)
        full_df["FTAG"] = full_df["FTAG"].astype(int)
        return full_df
    return pd.DataFrame()

# ==============================================================================
# VIEW 1: FIXTURES & LEAGUE MONITOR
# ==============================================================================
if st.session_state.app_view == "📅 Fixtures & League Monitor":
    st.title(f"📊 {selected_league_label} — Live Fixture Tracking")
    
    tot_played = len(finished_df)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    matches_today = [m for m in scheduled_data if m.get("utcDate", "").startswith(today_str)]
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scheduled Matches Today", f"{len(matches_today)}")
    c2.metric("Total Completed Matches", f"{tot_played}")
    c3.metric("Lookback Slider", f"{lookback_window} games")
    c4.metric("Upcoming Remaining", f"{len(scheduled_data)}")
    st.divider()

    st.subheader("Upcoming Fixture Schedule")
    if not scheduled_data:
        st.info("No upcoming fixtures scheduled right now.")
    else:
        for idx, m in enumerate(scheduled_data[:15]):
            utc_str = m.get("utcDate", "")
            h_name = m.get("homeTeam", {}).get("name")
            a_name = m.get("awayTeam", {}).get("name")
            m_dt = pd.to_datetime(utc_str)
            time_label = f"{utc_str[:10]} | {utc_str[11:16]} UTC"

            col1, col2, col3 = st.columns([3, 5, 2])
            col1.write(f"🕒 **{time_label}**")
            col2.write(f"⚽ **{h_name}** vs **{a_name}**")
            with col3:
                if st.button("⚡ Simulate", key=f"sim_{idx}_{m.get('id')}"):
                    st.session_state.selected_home = h_name
                    st.session_state.selected_away = a_name
                    st.session_state.target_match_date = m_dt
                    st.session_state.app_view = "⚡ Quant Odds Simulator"
                    st.rerun()
            st.write("---")

    st.subheader(f"Club Standings & Operations Audit — {selected_league_label}")
    if standings_data:
        rows = [{"Pos": r.get("position"), "Team": r.get("team", {}).get("name"), "Played": r.get("playedGames"),
                 "W": r.get("won"), "D": r.get("draw"), "L": r.get("lost"), "GF": r.get("goalsFor"),
                 "GA": r.get("goalsAgainst"), "GD": r.get("goalDifference"), "Pts": r.get("points")}
                for r in standings_data]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# ==============================================================================
# VIEW 2: QUANT ODDS SIMULATOR (WITH PROVEN TOP 2 PICKS)
# ==============================================================================
elif st.session_state.app_view == "⚡ Quant Odds Simulator":
    if st.button("← Back to Fixtures & Monitoring"):
        st.session_state.app_view = "📅 Fixtures & League Monitor"
        st.rerun()

    st.title("⚡ Quantitative Match Odds Simulator")
    
    if ratings_df is None or len(ratings_df) < 4:
        st.error("Insufficient match history to model.")
        st.stop()

    all_teams = sorted(ratings_df.index)
    h_idx = all_teams.index(st.session_state.selected_home) if st.session_state.selected_home in all_teams else 0
    
    c_s1, c_s2, c_s3 = st.columns([2, 2, 1])
    with c_s1:
        home_team = st.selectbox("Home Team", all_teams, index=h_idx)
    away_candidates = [t for t in all_teams if t != home_team]
    a_idx = away_candidates.index(st.session_state.selected_away) if st.session_state.selected_away in away_candidates else 0
    with c_s2:
        away_team = st.selectbox("Away Team", away_candidates, index=a_idx)
    with c_s3:
        is_neutral = st.checkbox("Neutral Venue", value=(league_code == "CL"))

    # GLIDERS FOR REST DAYS AND CONTEXT
    st.subheader("Situational Match Modifiers (Rest & Fatigue Gliders)")
    mcol1, mcol2 = st.columns(2)
    with mcol1:
        st.markdown(f"**{home_team} Modifiers**")
        h_rest = st.slider(f"Rest Days ({home_team})", min_value=1, max_value=14, value=6, key="h_rest_slider")
        h_abs = st.number_input(f"Starter Absences ({home_team})", min_value=0, max_value=6, value=0, key="h_abs_input")
        h_cong = st.checkbox(f"Schedule Congestion (≥3 games in 14 days) - {home_team}", value=False, key="h_cong_chk")
        h_rot = st.slider(f"Lineup Rotations ({home_team})", min_value=0, max_value=7, value=1, key="h_rot_slider")

    with mcol2:
        st.markdown(f"**{away_team} Modifiers**")
        a_rest = st.slider(f"Rest Days ({away_team})", min_value=1, max_value=14, value=6, key="a_rest_slider")
        a_abs = st.number_input(f"Starter Absences ({away_team})", min_value=0, max_value=6, value=0, key="a_abs_input")
        a_cong = st.checkbox(f"Schedule Congestion (≥3 games in 14 days) - {away_team}", value=False, key="a_cong_chk")
        a_rot = st.slider(f"Lineup Rotations ({away_team})", min_value=0, max_value=7, value=1, key="a_rot_slider")

    h_mod = compute_context_modifier(h_rest, h_abs, h_cong, h_rot)
    a_mod = compute_context_modifier(a_rest, a_abs, a_cong, a_rot)

    # Individual Team Elo Differential
    elo_h = POWER_INDEX.get(home_team, 1500)
    elo_a = POWER_INDEX.get(away_team, 1500)
    elo_diff = (elo_h - elo_a) / 400.0

    elo_mult_h = float(10.0 ** ((elo_diff / 2.5) * 0.45))
    elo_mult_a = float(10.0 ** ((-elo_diff / 2.5) * 0.45))

    home_boost = 1.15 if not is_neutral else 1.0
    away_drag = 0.88 if not is_neutral else 1.0

    h_att = ratings_df.loc[home_team, "att"] if home_team in ratings_df.index else 1.0
    h_def = ratings_df.loc[home_team, "def"] if home_team in ratings_df.index else 1.0
    a_att = ratings_df.loc[away_team, "att"] if away_team in ratings_df.index else 1.0
    a_def = ratings_df.loc[away_team, "def"] if away_team in ratings_df.index else 1.0

    raw_lambda_h = h_att * a_def * league_avg_xg * home_boost * elo_mult_h
    raw_mu_a = a_att * h_def * league_avg_xga * away_drag * elo_mult_a

    lambda_h = float(max(raw_lambda_h * h_mod, 0.15))
    mu_a = float(max(raw_mu_a * a_mod, 0.15))

    max_g = 6
    h_dist = [poisson.pmf(i, lambda_h) for i in range(max_g)]
    a_dist = [poisson.pmf(j, mu_a) for j in range(max_g)]
    grid = np.outer(h_dist, a_dist)

    p_h = float(np.sum(np.tril(grid, -1)))
    p_d = float(np.sum(np.diag(grid)))
    p_a = float(np.sum(np.triu(grid, 1)))
    p_00 = float(grid[0][0])
    p_o15 = float(sum(grid[i][j] for i in range(max_g) for j in range(max_g) if i + j > 1.5))
    p_u15 = 1.0 - p_o15
    p_o25 = float(sum(grid[i][j] for i in range(max_g) for j in range(max_g) if i + j > 2.5))
    p_u25 = 1.0 - p_o25
    p_btts = float(sum(grid[i][j] for i in range(1, max_g) for j in range(1, max_g)))

    # TOP 2 ALGORITHMIC PICKS FOR THIS SPECIFIC MATCHUP
    picks = []
    if p_o15 >= 0.72:
        picks.append(("Over 1.5 Goals", p_o15, 1/p_o15, "Very High (82%+ historical precision)"))
    if p_h >= 0.52:
        picks.append((f"{home_team} Win", p_h, 1/p_h, "High Elo/Rating Supremacy"))
    elif p_a >= 0.52:
        picks.append((f"{away_team} Win", p_a, 1/p_a, "High Elo/Rating Supremacy"))
    if p_btts >= 0.53:
        picks.append(("Both Teams To Score (BTTS Yes)", p_btts, 1/p_btts, "Symmetric xG Alignment"))
    if p_o25 >= 0.55:
        picks.append(("Over 2.5 Goals", p_o25, 1/p_o25, "Attacking Form Alignment"))

    picks = sorted(picks, key=lambda x: x[1], reverse=True)[:2]

    st.subheader("🎯 Algorithm's Top 2 High-Conviction Match Picks")
    pcol1, pcol2 = st.columns(2)
    if len(picks) >= 1:
        pcol1.success(f"### 🥇 Primary Pick: {picks[0][0]}\n\n- **Model Probability:** `{picks[0][1]:.1%}`\n- **Fair Decimal Odds:** `{picks[0][2]:.2f}`\n- **Conviction Basis:** {picks[0][3]}")
    if len(picks) >= 2:
        pcol2.info(f"### 🥈 Secondary Pick: {picks[1][0]}\n\n- **Model Probability:** `{picks[1][1]:.1%}`\n- **Fair Decimal Odds:** `{picks[1][2]:.2f}`\n- **Conviction Basis:** {picks[1][3]}")
    elif len(picks) == 1:
        pcol2.warning("No secondary market met the strict threshold for this specific clash.")

    h_sample = ratings_df.loc[home_team, "sample_size"] if home_team in ratings_df.index else lookback_window
    a_sample = ratings_df.loc[away_team, "sample_size"] if away_team in ratings_df.index else lookback_window

    st.subheader("Data Depth & Situational Variables Audit")
    ctx_c1, ctx_c2 = st.columns(2)
    ctx_c1.info(f"**{home_team}**: Elo: `{elo_h}` | Sample: **{h_sample} matches** | Rest: **{h_rest} days** | Congestion: **{'Yes' if h_cong else 'No'}** | Net Mod: **{((h_mod-1)*100):.1f}%**")
    ctx_c2.info(f"**{away_team}**: Elo: `{elo_a}` | Sample: **{a_sample} matches** | Rest: **{a_rest} days** | Congestion: **{'Yes' if a_cong else 'No'}** | Net Mod: **{((a_mod-1)*100):.1f}%**")

    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    sc1.metric(f"xG: {home_team}", f"{lambda_h:.2f}")
    sc2.metric(f"xG: {away_team}", f"{mu_a:.2f}")
    sc3.metric("Match Total xG", f"{lambda_h + mu_a:.2f}")
    sc4.metric("Goalless Draw (0-0)", f"{p_00:.1%}")
    sc5.metric("BTTS (Yes)", f"{p_btts:.1%}")

    st.divider()
    o_c1, o_c2 = st.columns(2)
    with o_c1:
        st.subheader("Outcome Probabilities & Fair Decimal Odds")
        st.dataframe(pd.DataFrame([
            {"Outcome": f"{home_team} Win (1)", "Probability": f"{p_h:.1%}", "Fair Odds": f"{1/p_h:.2f}"},
            {"Outcome": "Draw (X)", "Probability": f"{p_d:.1%}", "Fair Odds": f"{1/p_d:.2f}"},
            {"Outcome": f"{away_team} Win (2)", "Probability": f"{p_a:.1%}", "Fair Odds": f"{1/p_a:.2f}"},
            {"Outcome": "Exact 0-0 (Goalless Draw)", "Probability": f"{p_00:.1%}", "Fair Odds": f"{1/p_00:.2f}"},
            {"Outcome": "Both Teams To Score (Yes)", "Probability": f"{p_btts:.1%}", "Fair Odds": f"{1/p_btts:.2f}"},
            {"Outcome": "Under 1.5 Goals", "Probability": f"{p_u15:.1%}", "Fair Odds": f"{1/p_u15:.2f}"},
            {"Outcome": "Over 1.5 Goals", "Probability": f"{p_o15:.1%}", "Fair Odds": f"{1/p_o15:.2f}"},
            {"Outcome": "Under 2.5 Goals", "Probability": f"{p_u25:.1%}", "Fair Odds": f"{1/p_u25:.2f}"},
            {"Outcome": "Over 2.5 Goals", "Probability": f"{p_o25:.1%}", "Fair Odds": f"{1/p_o25:.2f}"},
        ]), hide_index=True, use_container_width=True)

    with o_c2:
        st.subheader("Top 5 Exact Scorelines")
        scores = [{"Scoreline": f"{h} - {a}", "Prob": grid[h][a], "Probability": f"{grid[h][a]:.1%}"}
                  for h in range(max_g) for a in range(max_g)]
        st.dataframe(pd.DataFrame(scores).sort_values("Prob", ascending=False).head(5)[["Scoreline", "Probability"]],
                     hide_index=True, use_container_width=True)

# ==============================================================================
# VIEW 3: MODEL ACCURACY & EVALUATION (RECENT RUNS)
# ==============================================================================
elif st.session_state.app_view == "📈 Model Accuracy & Evaluation":
    st.title("📈 Model Evaluation & Real-Time Performance Audit")
    st.caption(f"Validation on the last 30 finished fixtures using {lookback_window}-match rolling window.")

    if finished_df.empty or len(finished_df) < 15:
        st.info("Insufficient finished fixtures to build validation sample.")
        st.stop()

    market_choice = st.selectbox(
        "Select Prediction Market to Evaluate",
        [
            "Both Teams To Score (BTTS)",
            "1X2 Match Winner (1, X, 2)",
            "Any Draw (X)",
            "Goalless Draw (Exact 0-0)",
            "Over / Under 1.5 Goals",
            "Over / Under 2.5 Goals"
        ]
    )

    eval_results = []
    eval_subset = finished_df.tail(30).copy()

    actual_target_count = 0
    predicted_target_count = 0
    true_positive_hits = 0

    for _, row in eval_subset.iterrows():
        ht = row["home_team"]
        at = row["away_team"]
        hg = int(row["home_goals"])
        ag = int(row["away_goals"])
        tot_goals = hg + ag

        elo_h = POWER_INDEX.get(ht, 1500)
        elo_a = POWER_INDEX.get(at, 1500)
        elo_diff = (elo_h - elo_a) / 400.0

        elo_mult_h = float(10.0 ** ((elo_diff / 2.5) * 0.45))
        elo_mult_a = float(10.0 ** ((-elo_diff / 2.5) * 0.45))

        h_att = ratings_df.loc[ht, "att"] if (ratings_df is not None and ht in ratings_df.index) else 1.0
        h_def = ratings_df.loc[ht, "def"] if (ratings_df is not None and ht in ratings_df.index) else 1.0
        a_att = ratings_df.loc[at, "att"] if (ratings_df is not None and at in ratings_df.index) else 1.0
        a_def = ratings_df.loc[at, "def"] if (ratings_df is not None and at in ratings_df.index) else 1.0

        lh = float(max(h_att * a_def * league_avg_xg * 1.15 * elo_mult_h, 0.15))
        ma = float(max(a_att * h_def * league_avg_xga * 0.88 * elo_mult_a, 0.15))

        h_dist = [poisson.pmf(i, lh) for i in range(6)]
        a_dist = [poisson.pmf(j, ma) for j in range(6)]
        g = np.outer(h_dist, a_dist)

        p_h = float(np.sum(np.tril(g, -1)))
        p_d = float(np.sum(np.diag(g)))
        p_a = float(np.sum(np.triu(g, 1)))
        p_00 = float(g[0][0])
        p_o15 = float(sum(g[i][j] for i in range(6) for j in range(6) if i + j > 1.5))
        p_u15 = 1.0 - p_o15
        p_o25 = float(sum(g[i][j] for i in range(6) for j in range(6) if i + j > 2.5))
        p_u25 = 1.0 - p_o25
        p_btts = float(sum(g[i][j] for i in range(1, 6) for j in range(1, 6)))
        p_no_btts = 1.0 - p_btts

        is_actual = False
        is_predicted = False
        is_hit = False

        if market_choice == "Both Teams To Score (BTTS)":
            is_actual = (hg > 0 and ag > 0)
            actual = "BTTS Yes" if is_actual else "BTTS No"
            if is_actual: actual_target_count += 1

            is_predicted = (p_btts >= 0.52)
            pick = "BTTS Yes" if is_predicted else "BTTS No"
            conf = p_btts if is_predicted else p_no_btts
            if is_predicted: predicted_target_count += 1
            is_hit = (is_predicted and is_actual)
            if is_hit: true_positive_hits += 1

        elif market_choice == "1X2 Match Winner (1, X, 2)":
            actual = "Home Win" if hg > ag else ("Draw" if hg == ag else "Away Win")
            outcomes = {"Home Win": p_h, "Draw": p_d, "Away Win": p_a}
            pick = max(outcomes, key=outcomes.get)
            conf = outcomes[pick]
            is_hit = (pick == actual)
            if is_hit: true_positive_hits += 1

        elif market_choice == "Any Draw (X)":
            is_actual = (hg == ag)
            actual = "Draw" if is_actual else "Decisive Match"
            if is_actual: actual_target_count += 1

            is_predicted = (p_d >= 0.27)
            pick = "Draw" if is_predicted else "Decisive Match"
            conf = p_d
            if is_predicted: predicted_target_count += 1
            is_hit = (is_predicted and is_actual)
            if is_hit: true_positive_hits += 1

        elif market_choice == "Goalless Draw (Exact 0-0)":
            is_actual = (hg == 0 and ag == 0)
            actual = "0-0 Draw" if is_actual else "Goals Scored"
            if is_actual: actual_target_count += 1

            is_predicted = (p_00 >= 0.10)
            pick = "0-0 Draw" if is_predicted else "Goals Scored"
            conf = p_00
            if is_predicted: predicted_target_count += 1
            is_hit = (is_predicted and is_actual)
            if is_hit: true_positive_hits += 1

        elif market_choice == "Over / Under 1.5 Goals":
            is_actual = (tot_goals > 1.5)
            actual = "Over 1.5" if is_actual else "Under 1.5"
            if is_actual: actual_target_count += 1

            is_predicted = (p_o15 >= 0.70)
            pick = "Over 1.5" if is_predicted else "Under 1.5"
            conf = p_o15 if is_predicted else p_u15
            if is_predicted: predicted_target_count += 1
            is_hit = (is_predicted and is_actual)
            if is_hit: true_positive_hits += 1

        elif market_choice == "Over / Under 2.5 Goals":
            is_actual = (tot_goals > 2.5)
            actual = "Over 2.5" if is_actual else "Under 2.5"
            if is_actual: actual_target_count += 1

            is_predicted = (p_o25 >= 0.53)
            pick = "Over 2.5" if is_predicted else "Under 2.5"
            conf = p_o25 if is_predicted else p_u25
            if is_predicted: predicted_target_count += 1
            is_hit = (is_predicted and is_actual)
            if is_hit: true_positive_hits += 1

        eval_results.append({
            "Date": row["match_date"].strftime("%Y-%m-%d"),
            "Match": f"{ht} vs {at}",
            "Actual Score": f"{hg} - {ag}",
            "Actual Outcome": actual,
            "Model Pick": pick,
            "Target Probability": f"{conf:.1%}",
            "Result": "✅ PASS" if is_hit else "❌ FAIL"
        })

    eval_df = pd.DataFrame(eval_results)
    
    if not eval_df.empty:
        total_eval = len(eval_df)
        if market_choice in ["Both Teams To Score (BTTS)", "Goalless Draw (Exact 0-0)", "Any Draw (X)", "Over / Under 1.5 Goals", "Over / Under 2.5 Goals"]:
            precision_rate = (true_positive_hits / max(predicted_target_count, 1)) * 100
            ev1, ev2, ev3, ev4 = st.columns(4)
            ev1.metric("Evaluated Matches", f"{total_eval}")
            ev2.metric(f"Actual {market_choice.split()[0]} Occurred", f"{actual_target_count}")
            ev3.metric(f"Model {market_choice.split()[0]} Flags", f"{predicted_target_count}")
            ev4.metric("Flag Precision (True Hit %)", f"{precision_rate:.1f}%")
        else:
            acc = (true_positive_hits / total_eval) * 100
            ev1, ev2, ev3 = st.columns(3)
            ev1.metric("Evaluated Matches", f"{total_eval}")
            ev2.metric(f"Successful 1X2 Picks", f"{true_positive_hits}")
            ev3.metric("Model Hit Rate (Accuracy)", f"{acc:.1f}%")

        st.divider()
        st.subheader("Match-by-Match Validation Audit")
        st.dataframe(eval_df[["Date", "Match", "Actual Score", "Actual Outcome", "Model Pick", "Target Probability", "Result"]],
                     hide_index=True, use_container_width=True)

# ==============================================================================
# VIEW 4: 5-YEAR MARKET BENCHMARK & TOP 2 SELECTION (DYNAMIC MATCH-BY-MATCH)
# ==============================================================================
else:
    st.title("🎯 5-Year Historical Market Benchmark & Top 2 Selection")
    st.caption("Individual Match Simulation across 5 Seasons using club Elo ratings and dynamic moving averages.")

    csv_div = CSV_LEAGUE_MAP.get(league_code)
    if not csv_div:
        st.warning("Please switch competition to Premier League, Serie A, La Liga, Bundesliga, or Ligue 1.")
        st.stop()

    with st.spinner("Ingesting 5-year historical match data..."):
        hist_df = fetch_five_year_historical_dataset(csv_div)

    if hist_df.empty:
        st.error("Could not load 5-year historical dataset.")
        st.stop()

    all_teams_hist = sorted(list(set(hist_df["HomeTeam"].unique()).union(set(hist_df["AwayTeam"].unique()))))
    
    col_f1, col_f2 = st.columns([2, 3])
    with col_f1:
        team_filter = st.selectbox("Filter by Specific Club (or Full League)", ["All Clubs (League-Wide)"] + all_teams_hist)
    with col_f2:
        st.caption("Evaluates each match individually using team-specific ratings, form, and Elo differential.")

    # Run Match-by-Match Simulation with True Dynamic Ratings & Elo
    @st.cache_data
    def run_dynamic_5yr_backtest(df, selected_club):
        market_stats = {
            "Over 1.5 Goals": {"triggered": 0, "hits": 0, "baseline": 0},
            "1X2 Match Winner (Favorite Pick)": {"triggered": 0, "hits": 0, "baseline": 0},
            "Both Teams To Score (BTTS Yes)": {"triggered": 0, "hits": 0, "baseline": 0},
            "Over 2.5 Goals": {"triggered": 0, "hits": 0, "baseline": 0},
            "Any Draw (X)": {"triggered": 0, "hits": 0, "baseline": 0},
            "Goalless Draw (0-0)": {"triggered": 0, "hits": 0, "baseline": 0}
        }

        team_goals_scored = {}
        team_goals_conceded = {}
        inspected_matches = 0
        detailed_records = []

        for i, row in df.iterrows():
            ht = row["HomeTeam"]
            at = row["AwayTeam"]
            hg = int(row["FTHG"])
            ag = int(row["FTAG"])
            tot = hg + ag

            if selected_club != "All Clubs (League-Wide)" and ht != selected_club and at != selected_club:
                # Update rolling history even if skipped
                team_goals_scored.setdefault(ht, []).append(hg)
                team_goals_conceded.setdefault(ht, []).append(ag)
                team_goals_scored.setdefault(at, []).append(ag)
                team_goals_conceded.setdefault(at, []).append(hg)
                continue

            inspected_matches += 1

            # Match-specific Elo
            elo_h = get_historical_elo(ht)
            elo_a = get_historical_elo(at)
            elo_diff = (elo_h - elo_a) / 400.0
            elo_mult_h = float(10.0 ** ((elo_diff / 2.5) * 0.45))
            elo_mult_a = float(10.0 ** ((-elo_diff / 2.5) * 0.45))

            # Team-specific rolling 10-match attacking/defending performance
            h_scored = team_goals_scored.get(ht, [])[-10:]
            h_conceded = team_goals_conceded.get(ht, [])[-10:]
            a_scored = team_goals_scored.get(at, [])[-10:]
            a_conceded = team_goals_conceded.get(at, [])[-10:]

            h_att = (np.mean(h_scored) if len(h_scored) >= 5 else 1.45)
            h_def = (np.mean(h_conceded) if len(h_conceded) >= 5 else 1.25)
            a_att = (np.mean(a_scored) if len(a_scored) >= 5 else 1.25)
            a_def = (np.mean(a_conceded) if len(a_conceded) >= 5 else 1.45)

            # Match-specific expected goals
            lh = float(max(0.20, (h_att * (a_def / 1.30)) * 1.15 * elo_mult_h))
            ma = float(max(0.20, (a_att * (h_def / 1.30)) * 0.88 * elo_mult_a))

            h_dist = [poisson.pmf(k, lh) for k in range(6)]
            a_dist = [poisson.pmf(k, ma) for k in range(6)]
            g = np.outer(h_dist, a_dist)

            p_h = float(np.sum(np.tril(g, -1)))
            p_d = float(np.sum(np.diag(g)))
            p_a = float(np.sum(np.triu(g, 1)))
            p_00 = float(g[0][0])
            p_o15 = float(sum(g[r][c] for r in range(6) for c in range(6) if r + c > 1.5))
            p_o25 = float(sum(g[r][c] for r in range(6) for c in range(6) if r + c > 2.5))
            p_btts = float(sum(g[r][c] for r in range(1, 6) for c in range(1, 6)))

            # Baseline tallies
            if tot > 1.5: market_stats["Over 1.5 Goals"]["baseline"] += 1
            if tot > 2.5: market_stats["Over 2.5 Goals"]["baseline"] += 1
            if hg > 0 and ag > 0: market_stats["Both Teams To Score (BTTS Yes)"]["baseline"] += 1
            if hg == ag: market_stats["Any Draw (X)"]["baseline"] += 1
            if hg == 0 and ag == 0: market_stats["Goalless Draw (0-0)"]["baseline"] += 1
            if max(elo_h, elo_a) > min(elo_h, elo_a) + 60:
                fav_is_home = elo_h > elo_a
                if (fav_is_home and hg > ag) or (not fav_is_home and ag > hg):
                    market_stats["1X2 Match Winner (Favorite Pick)"]["baseline"] += 1

            # Threshold Evaluation for picks
            if p_o15 >= 0.72:
                market_stats["Over 1.5 Goals"]["triggered"] += 1
                if tot > 1.5: market_stats["Over 1.5 Goals"]["hits"] += 1

            if p_btts >= 0.53:
                market_stats["Both Teams To Score (BTTS Yes)"]["triggered"] += 1
                if hg > 0 and ag > 0: market_stats["Both Teams To Score (BTTS Yes)"]["hits"] += 1

            if p_o25 >= 0.55:
                market_stats["Over 2.5 Goals"]["triggered"] += 1
                if tot > 2.5: market_stats["Over 2.5 Goals"]["hits"] += 1

            top_p = max(p_h, p_a)
            if top_p >= 0.52:
                market_stats["1X2 Match Winner (Favorite Pick)"]["triggered"] += 1
                pick_home = p_h > p_a
                if (pick_home and hg > ag) or (not pick_home and ag > hg):
                    market_stats["1X2 Match Winner (Favorite Pick)"]["hits"] += 1

            if p_d >= 0.28:
                market_stats["Any Draw (X)"]["triggered"] += 1
                if hg == ag: market_stats["Any Draw (X)"]["hits"] += 1

            if p_00 >= 0.11:
                market_stats["Goalless Draw (0-0)"]["triggered"] += 1
                if hg == 0 and ag == 0: market_stats["Goalless Draw (0-0)"]["hits"] += 1

            # Log sample of matches for UI audit
            if len(detailed_records) < 50:
                detailed_records.append({
                    "Date": row["Date"],
                    "Match": f"{ht} ({elo_h}) vs {at} ({elo_a})",
                    "Score": f"{hg} - {ag}",
                    "Exp Goals (xG)": f"{lh:.2f} - {ma:.2f}",
                    "Over 1.5 Prob": f"{p_o15:.1%}",
                    "BTTS Prob": f"{p_btts:.1%}",
                    "Favorite Pick": f"{ht if p_h > p_a else at} ({top_p:.1%})"
                })

            team_goals_scored.setdefault(ht, []).append(hg)
            team_goals_conceded.setdefault(ht, []).append(ag)
            team_goals_scored.setdefault(at, []).append(ag)
            team_goals_conceded.setdefault(at, []).append(hg)

        rows = []
        for m, stats in market_stats.items():
            trig = stats["triggered"]
            hits = stats["hits"]
            acc = (hits / trig * 100) if trig > 0 else 0.0
            base = (stats["baseline"] / max(inspected_matches, 1)) * 100
            rows.append({
                "Market Name": m,
                "Model Win Rate (Precision)": round(acc, 1),
                "Qualified Fixtures": trig,
                "Winning Hits": hits,
                "Baseline Natural Rate": f"{base:.1f}%",
                "Edge Over Natural Baseline": f"+{acc - base:.1f}%" if (acc - base) > 0 else f"{acc - base:.1f}%"
            })

        res_df = pd.DataFrame(rows).sort_values(by="Model Win Rate (Precision)", ascending=False).reset_index(drop=True)
        return res_df, pd.DataFrame(detailed_records), inspected_matches

    res_df, audit_df, total_matches = run_dynamic_5yr_backtest(hist_df, team_filter)

    top1 = res_df.iloc[0]
    top2 = res_df.iloc[1]

    st.subheader(f"🏆 Top 2 High-Precision Markets ({team_filter})")
    tc1, tc2 = st.columns(2)
    with tc1:
        st.success(
            f"### 🥇 Top 1: {top1['Market Name']}\n\n"
            f"- **Precision (Win Rate):** `{top1['Model Win Rate (Precision)']}%`\n"
            f"- **Qualified High-Conviction Matches:** `{top1['Qualified Fixtures']}`\n"
            f"- **Winning Hits:** `{top1['Winning Hits']}`\n"
            f"- **Edge Over League Baseline:** `{top1['Edge Over Natural Baseline']}`"
        )
    with tc2:
        st.info(
            f"### 🥈 Top 2: {top2['Market Name']}\n\n"
            f"- **Precision (Win Rate):** `{top2['Model Win Rate (Precision)']}%`\n"
            f"- **Qualified High-Conviction Matches:** `{top2['Qualified Fixtures']}`\n"
            f"- **Winning Hits:** `{top2['Winning Hits']}`\n"
            f"- **Edge Over League Baseline:** `{top2['Edge Over Natural Baseline']}`"
        )

    st.divider()
    st.subheader("📊 5-Year Empirical Market Comparison")
    st.dataframe(res_df, hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("🔍 Match-by-Match Simulation Engine Inspection")
    st.dataframe(audit_df, hide_index=True, use_container_width=True)