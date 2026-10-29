import requests

# Put your API key between the quotes below
API_KEY = "YOUR_API_KEY_HERE"

headers = {"X-Auth-Token": "53eda6d8b3e840f3b4253486531061bf"}
base_url = "https://api.football-data.org/v4/competitions"

response = requests.get(base_url, headers=headers)

if response.status_code == 200:
    data = response.json()
    available_codes = [c["code"] for c in data.get("competitions", []) if c.get("code")]
    print("--- SUCCESS ---")
    print(f"Status Code: {response.status_code}")
    print("Leagues detected in your tier:")
    print(", ".join(available_codes))
else:
    print(f"Failed with status code: {response.status_code}")
    print(response.text)