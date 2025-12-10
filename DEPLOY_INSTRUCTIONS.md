# 🚀 Déploiement en Une Commande

Ce guide vous permet de déployer le bot PumpFun sur un VPS Ubuntu vierge en **UNE SEULE COMMANDE**.

---

## ✅ Prérequis

- **VPS Ubuntu 22.04 ou 24.04** (fraîchement installé)
- **Accès SSH root**
- **Git installé sur le VPS** (généralement préinstallé)

---

## 🎯 Déploiement Rapide

### Option 1 : Depuis votre VPS (Recommandé)

Connectez-vous à votre VPS et exécutez :

```bash
curl -fsSL https://raw.githubusercontent.com/supermerou03101983/pumpfun-bot/main/deploy_non_interactive.sh | sudo bash
```

**OU** si vous préférez télécharger d'abord :

```bash
git clone https://github.com/supermerou03101983/pumpfun-bot.git
cd pumpfun-bot
chmod +x deploy_non_interactive.sh
sudo ./deploy_non_interactive.sh
```

### Option 2 : Depuis votre machine locale (SSH)

Si vous avez `sshpass` installé :

```bash
sshpass -p "VOTRE_MOT_DE_PASSE" ssh root@VOTRE_IP "curl -fsSL https://raw.githubusercontent.com/supermerou03101983/pumpfun-bot/main/deploy_non_interactive.sh | bash"
```

---

## 📋 Ce que fait le script

Le script `deploy_non_interactive.sh` effectue automatiquement :

1. ✅ Détection de l'OS (Ubuntu 22.04/24.04)
2. ✅ Installation des dépendances système
   - Python 3.11 (Ubuntu 22.04) ou 3.12 (Ubuntu 24.04)
   - Redis
   - Age (chiffrement)
   - Build tools
3. ✅ Configuration Python venv
4. ✅ Installation des packages Python
5. ✅ Génération des clés age (chiffrement)
6. ✅ Configuration automatique
7. ✅ Création d'un wallet de test (pour paper trading)
8. ✅ Installation des services systemd
9. ✅ Démarrage du bot + dashboard
10. ✅ Configuration du pare-feu

---

## 🔍 Vérification du Déploiement

### 1. Vérifier les services

```bash
systemctl status pumpfun-bot
systemctl status pumpfun-dashboard
```

### 2. Accéder au Dashboard

Ouvrez dans votre navigateur :
```
http://VOTRE_IP:8501
```

### 3. Vérifier la santé du bot

```bash
curl http://localhost:8080/health
```

Sortie attendue :
```json
{
  "status": "healthy",
  "mode": "paper",
  "uptime_seconds": 120,
  "active_positions": 0,
  "redis_connected": true
}
```

### 4. Voir les logs en temps réel

```bash
# Logs du bot
journalctl -u pumpfun-bot -f

# Logs du dashboard
journalctl -u pumpfun-dashboard -f
```

---

## ⚙️ Configuration Personnalisée (Optionnel)

Par défaut, le script utilise des valeurs de test. Pour personnaliser :

### 1. Éditer la configuration

```bash
nano /opt/pumpfun-bot/config/config.yaml
```

### 2. Configurer votre clé API Helius

Remplacez `your_helius_api_key_here` par votre vraie clé de [helius.dev](https://helius.dev)

### 3. Remplacer le wallet de test (pour live trading)

```bash
cd /opt/pumpfun-bot
source venv/bin/activate
python scripts/encrypt_key.py
```

### 4. Redémarrer le bot

```bash
systemctl restart pumpfun-bot
```

---

## 🔧 Dépannage

### Le bot ne démarre pas

```bash
# Voir les dernières erreurs
journalctl -u pumpfun-bot -n 50 --no-pager

# Vérifier la configuration
cat /opt/pumpfun-bot/config/config.yaml

# Vérifier Redis
systemctl status redis-server
```

### Le dashboard n'est pas accessible

```bash
# Vérifier le pare-feu
sudo ufw status

# Ouvrir le port si nécessaire
sudo ufw allow 8501/tcp
```

### Erreur de déchiffrement du wallet

```bash
# Vérifier que la clé age existe
ls -la /root/.config/sops/age/keys.txt

# Recréer le wallet de test
echo "test-key" | age -e -i /root/.config/sops/age/keys.txt -o /opt/pumpfun-bot/config/trading_wallet.enc
```

---

## 📊 Mode Paper vs Live

### Mode actuel (Paper - Sûr)

Par défaut, le bot fonctionne en **mode paper** :
- ✅ Aucune transaction réelle
- ✅ Simulations avec prix réels
- ✅ Enregistrement P&L dans Redis
- ✅ Aucun risque financier

### Passer en mode Live (Attention !)

⚠️ **DANGER** : Mode live = vraies transactions = argent réel

1. Éditer `/opt/pumpfun-bot/config/config.yaml`
   ```yaml
   trading_mode: live  # Changer de 'paper' à 'live'
   ```

2. Définir la variable d'environnement (sécurité)
   ```bash
   echo 'Environment="LIVE_MODE_CONFIRMED=true"' >> /etc/systemd/system/pumpfun-bot.service
   systemctl daemon-reload
   ```

3. Configurer votre VRAI wallet
   ```bash
   cd /opt/pumpfun-bot
   source venv/bin/activate
   python scripts/encrypt_key.py
   # Entrez votre vraie clé privée Solana
   ```

4. Redémarrer
   ```bash
   systemctl restart pumpfun-bot
   ```

---

## 🎛️ Commandes Utiles

```bash
# Redémarrer les services
systemctl restart pumpfun-bot
systemctl restart pumpfun-dashboard

# Arrêter les services
systemctl stop pumpfun-bot
systemctl stop pumpfun-dashboard

# Voir les logs des 100 dernières lignes
journalctl -u pumpfun-bot -n 100

# Mettre à jour le code
cd /opt/pumpfun-bot
git pull
systemctl restart pumpfun-bot
systemctl restart pumpfun-dashboard

# Vérifier l'utilisation mémoire/CPU
systemctl status pumpfun-bot
systemctl status pumpfun-dashboard
```

---

## 📈 Performances Attendues

Après un déploiement réussi, vous devriez voir :

- **Bot** : État "active (running)"
- **Dashboard** : Accessible sur le port 8501
- **RAM** : ~800 MB utilisés (bot + dashboard)
- **CPU** : <5% en idle, jusqu'à 20% lors de la détection de tokens
- **Logs** : Format JSON structuré

---

## 🆘 Support

Si le déploiement échoue :

1. Vérifiez les logs : `journalctl -u pumpfun-bot -n 100`
2. Vérifiez l'OS : `cat /etc/os-release` (doit être Ubuntu 22.04 ou 24.04)
3. Vérifiez les permissions : `ls -la /opt/pumpfun-bot`
4. Réinstallez Redis : `systemctl restart redis-server`

---

## ✅ Checklist Post-Déploiement

- [ ] Services démarrés (`systemctl status pumpfun-bot`)
- [ ] Dashboard accessible (`http://VOTRE_IP:8501`)
- [ ] Health check OK (`curl http://localhost:8080/health`)
- [ ] Logs sans erreur (`journalctl -u pumpfun-bot -n 20`)
- [ ] Mode confirmé PAPER (`grep trading_mode /opt/pumpfun-bot/config/config.yaml`)

---

**🎉 Votre bot est opérationnel !**

Accédez au dashboard pour voir les statistiques en temps réel :
**http://VOTRE_IP:8501**
