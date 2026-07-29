# Unzip Bot — Setup Guide

Ye bot zip file ko download → extract → channel par upload karta hai.

## ⚠️ Sabse zaroori baat: 2GB support

Telegram ka **default** Bot API sirf:
- Download: max 20MB
- Upload: max 50MB

allow karta hai. **2GB tak ki files ke liye aapko apna khud ka Local Bot API
Server chalana padega.** Bina iske, ye code sirf 20MB/50MB tak ki files hi
process kar payega.

### Local Bot API Server chalana (Docker se sabse aasan)

```bash
docker run -d \
  -p 8081:8081 \
  -v telegram-bot-api-data:/var/lib/telegram-bot-api \
  -e TELEGRAM_API_ID=<your_api_id> \
  -e TELEGRAM_API_HASH=<your_api_hash> \
  -e TELEGRAM_LOCAL=1 \
  --name telegram-bot-api \
  aiogram/telegram-bot-api:latest
```

`TELEGRAM_API_ID` aur `TELEGRAM_API_HASH` https://my.telegram.org par apna
app banake milta hai.

Server chalne ke baad ye `http://localhost:8081` par available hoga — yahi
`LOCAL_API_URL` env variable me daalna hai.

Agar aap Render/Railway/VPS pe deploy kar rahe hain, to local Bot API server
ko bhi ek separate service/container ke roop me wahi machine par chalana
hoga (dono ko saath rehna zaroori hai).

## Installation

```bash
pip install -r requirements.txt
```

## Environment Variables

| Variable       | Kya hai                                            |
|----------------|-----------------------------------------------------|
| `API_ID`       | my.telegram.org se milega                           |
| `API_HASH`     | my.telegram.org se milega                           |
| `BOT_TOKEN`    | @BotFather se milega                                |
| `CHANNEL_ID`   | Jis channel me files bhejni hain (numeric ID/@username) |
| `LOCAL_SERVER` | `true`/`false` — local Bot API server use karna hai ya nahi |
| `LOCAL_API_URL`| Default: `http://localhost:8081`                    |

Bot ko us channel me **admin** banana na bhoolein jaha files bhejni hain.

## Run

```bash
export API_ID=1234567
export API_HASH=xxxxxxxxxxxxxxxx
export BOT_TOKEN=xxxxxxxxxx:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export CHANNEL_ID=-1001234567890
export LOCAL_SERVER=true
export LOCAL_API_URL=http://localhost:8081

python bot.py
```

## Coolify pe deploy karna (recommended tarika)

Coolify me sabse aasan aur sahi tarika hai **Docker Compose** resource use
karna — isse `unzip-bot` aur `telegram-api` dono ek hi internal network me
aa jate hain aur bot `localhost` ki jagah service-name (`telegram-api`) se
connect kar leta hai.

1. **Repo/files ready karein**: `Dockerfile`, `docker-compose.yml`,
   `bot.py`, `requirements.txt` — ye sab ek hi folder/repo me hone chahiye
   (jaisa is zip me diya hai). Ise apne GitHub repo me push kar dein, ya
   Coolify me "Docker Compose" ke through directly paste kar sakte hain.

2. **Coolify me naya resource banayein**:
   - Project open karein → **+ New Resource** → **Docker Compose**
   - Agar GitHub repo use kar rahe hain to us repo ko connect karein
   - Agar seedha paste karna hai to `docker-compose.yml` ka content wahi
     daal dein

3. **Environment variables set karein** (Coolify ke "Environment
   Variables" tab me):
   ```
   API_ID=1234567
   API_HASH=xxxxxxxxxxxxxxxxxxxxx
   BOT_TOKEN=xxxxxxxxxx:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   CHANNEL_ID=-1001234567890
   ```
   (`docker-compose.yml` andar hi `${API_ID}` jaise variables inhi ko
   utha lenge — alag se kuch aur set karne ki zaroorat nahi)

4. **Deploy dabayein**. Coolify dono containers (`telegram-api` aur
   `unzip-bot`) build/pull karke start kar dega, same network pe.

5. **Verify karein**: Coolify ke logs section me `unzip-bot` service ke
   logs dekhein — `"Starting unzip bot..."` dikhna chahiye bina kisi
   connection error ke.

### Zaroori dhyan rakhein
- Bot ko target channel me **admin** banana na bhoolein.
- VPS me kam se kam **4GB+ RAM** aur bahut zyada extra disk space rakhein
  (download + extract, dono ke liye 2GB tak space use ho sakta hai — ek
  hi time pe do zip aayi to 4GB+ tak use ho sakta hai).
- `telegram-api` service ka port **publish/expose na karein** bahar — ye
  sirf `unzip-bot` ke liye internal hona chahiye, security ke liye.
- Persistent volumes (`docker-compose.yml` me diye gaye hain) restart ke
  baad bhi data safe rakhte hain — inhe hataye nahi.

## Kaise use karein

1. Bot ko private chat me `/start` bhejein
2. Koi bhi `.zip` file bhejein (2GB tak, local server ke saath)
3. Bot download → extract → har file channel par upload kar dega
4. Extraction ke baad temp files khud delete ho jati hain

## Limitations / Notes

- Sirf top-level `.zip` files support hain — nested zip ke andar zip khud
  extract nahi hoti (chaho to recursive extraction add karwa sakte hain).
- Password-protected zip abhi supported nahi hai.
- Har individual extracted file bhi Telegram ki upload limit (2GB, local
  server ke saath) ke andar honi chahiye.
- Bahut zyada files (jaise 500+) ek zip me hone par Telegram flood-wait laga
  sakta hai — bot me `FloodWait` handling already daali gayi hai, bas thoda
  time lagega.
