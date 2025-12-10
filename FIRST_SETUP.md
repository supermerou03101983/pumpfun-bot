# 🚀 First Setup Guide

This guide walks you through the initial Git setup for the PumpFun Bot project.

## Prerequisites

- VS Code installed
- Git installed (`git --version` should work)
- GitHub account with repository created at: https://github.com/supermerou03101983/pumpfun-bot.git

## Step-by-Step Setup

### 1. Verify All Files Are Present

Check that your project directory contains:
```
.gitignore
requirements.txt
README.md
deploy.sh
config/
src/
scripts/
systemd/
```

### 2. Initialize Git Repository

Open terminal in VS Code (`` Ctrl+` `` or `` Cmd+` ``) and run:

```bash
git init
```

This creates a `.git` folder and initializes version control.

### 3. Stage All Files

Add all files to the staging area:

```bash
git add .
```

Verify what will be committed:
```bash
git status
```

You should see all files in green (staged), and `config/trading_wallet.enc` should NOT appear (it's gitignored).

### 4. Create Initial Commit

```bash
git commit -m "feat: v1 initial commit — paper trading + dashboard + one-click deploy"
```

### 5. Link to Remote Repository

Add your GitHub repository as the remote origin:

```bash
git remote add origin https://github.com/supermerou03101983/pumpfun-bot.git
```

Verify the remote:
```bash
git remote -v
```

### 6. Push to GitHub

Push your code to the main branch:

```bash
git push -u origin main
```

If your default branch is `master`, use:
```bash
git branch -M main
git push -u origin main
```

You may be prompted to authenticate with GitHub (use Personal Access Token or SSH key).

## Common Issues

### "Repository not found"
- Ensure the repository exists on GitHub
- Check your GitHub authentication (run `git credential-helper` or set up SSH keys)

### "Permission denied"
- Generate a Personal Access Token: GitHub → Settings → Developer settings → Personal access tokens → Generate new token
- Use the token as your password when prompted

### "Branch 'main' does not exist"
- Some repos default to `master`. Rename: `git branch -M main`

## Next Steps

Once your code is on GitHub:

1. **Deploy to VPS**: SSH into your Ubuntu server and run:
   ```bash
   git clone https://github.com/supermerou03101983/pumpfun-bot.git
   cd pumpfun-bot
   chmod +x deploy.sh
   sudo ./deploy.sh
   ```

2. **Paper Trading**: The bot starts in PAPER mode by default (no real trades)

3. **Access Dashboard**: Open `http://<your-vps-ip>:8501` in your browser

## Git Workflow Tips

### Making Changes
```bash
# Edit files in VS Code
git add .
git commit -m "fix: description of your changes"
git push
```

### Pulling Updates on VPS
```bash
ssh your-vps
cd /opt/pumpfun-bot  # or wherever you cloned it
git pull
sudo systemctl restart pumpfun-bot
sudo systemctl restart pumpfun-dashboard
```

### Viewing Commit History
```bash
git log --oneline --graph --all
```

## Security Reminders

- ✅ `trading_wallet.enc` is gitignored (encrypted wallet never pushed)
- ✅ `config.yaml` is gitignored (API keys stay local)
- ✅ Only `config.example.yaml` is committed (template without secrets)
- ⚠️ NEVER commit your private key or API keys
- ⚠️ Always verify `.gitignore` before `git add .`

## Support

If you encounter issues:
1. Check `deploy.sh` logs for deployment errors
2. Review `journalctl -u pumpfun-bot -f` for bot runtime issues
3. Ensure all dependencies are installed (`pip install -r requirements.txt`)

---

**[✅] You're ready to build!** Follow the steps above, then deploy to your VPS.
