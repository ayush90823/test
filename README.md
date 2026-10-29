# Telegram Video Stream / Embed Bot (GitHub Actions + Quick Tunnel)

Bot ko video bhejo -> fixed player link aur iframe code milta hai.
Koi card ya Cloudflare account nahi chahiye.

## Kaise kaam karta hai

1. GitHub Actions bot + web server chalata hai (har 6 ghante me restart).
2. Cloudflare **quick tunnel** server ko internet par laata hai. Iska URL har restart par badalta hai.
3. Workflow naya URL `tunnel` branch ki `url.json` me save karta hai.
4. `docs/index.html` (GitHub Pages) ek **fixed** player page hai. Wo `url.json` padh kar
   latest tunnel se video chalata hai. Isliye aapka embed link kabhi nahi badalta.

Video ka data seedha tunnel se viewer tak jata hai, GitHub Pages se nahi.

## Setup

1. **API keys**: https://my.telegram.org -> API development tools -> `API_ID`, `API_HASH`
2. **Bot**: @BotFather se bot banao -> `BOT_TOKEN`
3. **Storage channel**: ek private channel banao, bot ko usme **admin** banao.
   Channel ID `-100xxxxxxxxxx` format me chahiye (@userinfobot / @RawDataBot se mil jayegi).
4. **GitHub repo** (public) banao aur ye saari files push karo.
5. **GitHub Pages on karo**: Settings -> Pages -> Source: *Deploy from a branch* ->
   Branch: `main`, Folder: `/docs` -> Save.
   Player URL hoga: `https://<username>.github.io/<repo>/`
6. **Secrets** (Settings -> Secrets and variables -> Actions):
   `API_ID`, `API_HASH`, `BOT_TOKEN`, `BIN_CHANNEL`, `SECRET_KEY`, `ALLOWED_USERS`
   (`SECRET_KEY` baad me mat badalna, warna purane links band ho jayenge)
7. **Actions** tab -> "Run Stream Bot" -> Run workflow.

## Website me lagana

```html
<iframe src="https://<username>.github.io/<repo>/?id=123&hash=abcd1234abcd1234"
        width="640" height="360" frameborder="0" allowfullscreen></iframe>
```

(Bot ye iframe code khud bana kar deta hai.)

## Notes

- Har 6 ghante restart par kuch minute video nahi chalega; player khud dobara try karta rehta hai.
- Quick tunnel Cloudflare ki taraf se "testing" ke liye hai, uptime ki guarantee nahi.
- Browser me MP4 (H.264/AAC) reliably chalta hai. MKV/AVI kai browsers me nahi chalte.
- `ALLOWED_USERS` set karo warna koi bhi aapka bot use kar sakta hai.
- `.env` file kabhi commit mat karna.
- Sirf wahi video use karo jiske rights aapke paas hain.
