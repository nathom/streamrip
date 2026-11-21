sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
sudo mkdir -p -m 755 /etc/apt/sources.list.d
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
sudo apt update
sudo apt install gh

curl -fsSL https://gh.io/copilot-install | bash
copilot plugin marketplace add https://github.com/ayghri/i-have-adhd.git
copilot plugin marketplace add https://github.com/obra/superpowers.git
copilot plugin add i-have-adhd@i-have-adhd
copilot plugin add superpowers@superpowers-dev