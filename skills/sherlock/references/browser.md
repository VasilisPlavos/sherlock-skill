# Browser checks

Plain HTTP misses login-walled platforms and anything that returned `WAF`. Treat these as browser-only regardless of the CSV: **LinkedIn, Facebook, Instagram, X/Twitter, TikTok, Threads** — and use their **people search by name**, not only username URLs (LinkedIn slugs are often `first-last-1a2b3c`).

First find what is available — do not ask before looking.

bash:

```bash
for b in chromium chromium-browser google-chrome google-chrome-stable firefox msedge; do command -v "$b"; done
for p in "/c/Program Files/Google/Chrome/Application/chrome.exe" "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
         "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" "/c/Program Files/Mozilla Firefox/firefox.exe" \
         "/Applications/Google Chrome.app" "/Applications/Firefox.app" "/Applications/Microsoft Edge.app"; do
  [ -e "$p" ] && echo "$p"
done
<PY> -c "import playwright; print('python playwright')" 2>/dev/null
npx --no-install playwright --version 2>/dev/null
```

PowerShell:

```powershell
'chrome', 'msedge', 'firefox', 'chromium' | ForEach-Object { (Get-Command $_ -ErrorAction SilentlyContinue).Source }
"$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
"$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
"$env:ProgramFiles\Mozilla Firefox\firefox.exe" | Where-Object { Test-Path $_ }
<PY> -c "import playwright; print('python playwright')" 2>$null
npx --no-install playwright --version 2>$null
```

Also check your own tool list for browser tools (names containing `chrome`, `browser`, `playwright`, `puppeteer`, `browseros`). An installed desktop browser alone is not automatable; it matters for extension-based tools and for Playwright's `chrome`/`msedge` channels.

Present **only what you found**, with trade-offs, and let the user choose:

| Option | Logged in? | Trade-off |
|---|---|---|
| Browser extension tools in the user's own browser | yes, as the user | best coverage; lookups come from the user's real accounts |
| Dedicated agent browser (e.g. BrowserOS) | whatever the user signed into it | separate profile; same visibility caveat if signed in |
| Playwright / headless browser | no (unless the user logs in once in a persistent profile) | clean; login walls stay closed |
| None / skip | — | report lists these sites as unchecked |

Tell the user before choosing: **signed-in visits can be visible to the person** (LinkedIn's "Who viewed your profile" unless private mode is on; story/profile views elsewhere). Never log in, enter credentials or solve CAPTCHAs on the user's behalf — ask them to do it.

Record each browser finding as an extra `CLAIMED` (site, URL, username) for step 5.
