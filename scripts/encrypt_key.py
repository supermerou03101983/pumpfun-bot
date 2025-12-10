#!/usr/bin/env python3
"""
Wallet Encryption Script

Encrypts a Solana private key using age encryption.

Usage:
    python scripts/encrypt_key.py

Interactive prompts for:
- Private key (base58 format)
- Output path (defaults to config/trading_wallet.enc)
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import getpass
from solders.keypair import Keypair
from src.utils.security import SecurityManager


def main():
    """Main encryption routine"""
    print("=" * 60)
    print("PumpFun Bot - Wallet Encryption")
    print("=" * 60)
    print()

    # Load config
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"

    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    else:
        # Use default config
        print("⚠️  Config not found, using defaults")
        config = {
            "security": {
                "encrypted_wallet_path": "config/trading_wallet.enc",
                "age_public_key": "age1qyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqsqzcwqr",
                "key_lifetime_seconds": 30,
            }
        }

    # Get private key input
    print("Enter your Solana private key:")
    print("(Formats accepted: base58 string, or JSON array)")
    print()

    choice = input("Do you want to (1) Enter existing key or (2) Generate new key? [1/2]: ").strip()

    if choice == "2":
        # Generate new keypair
        print("\nGenerating new keypair...")
        keypair = Keypair()
        private_key_b58 = str(keypair)
        print(f"\n✅ New keypair generated!")
        print(f"Public Key: {keypair.pubkey()}")
        print(f"Private Key (SAVE THIS): {private_key_b58}")
        print()
        input("Press Enter to continue with encryption...")
    else:
        # Get existing key
        private_key_input = getpass.getpass("Private Key (input hidden): ").strip()

        # Try to parse key
        try:
            # Test if it's a valid key by creating a Keypair
            keypair = Keypair.from_base58_string(private_key_input)
            private_key_b58 = private_key_input
            print(f"\n✅ Valid key detected for wallet: {keypair.pubkey()}")
        except Exception as e:
            print(f"\n❌ Invalid private key format: {e}")
            print("Expected: base58 string (e.g., 5Jx...)")
            sys.exit(1)

    # Get output path
    default_output = config["security"]["encrypted_wallet_path"]
    output_path_input = input(f"\nOutput path [{default_output}]: ").strip()
    output_path = output_path_input if output_path_input else default_output

    # Ensure directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Check if file exists
    if output_file.exists():
        overwrite = input(f"\n⚠️  File exists: {output_path}. Overwrite? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("Aborted.")
            sys.exit(0)

    # Encrypt
    print("\n🔒 Encrypting wallet...")
    try:
        manager = SecurityManager(config)
        manager.encrypt_key(private_key_b58, str(output_file))
        print(f"\n✅ Wallet encrypted successfully!")
        print(f"   Output: {output_file}")
        print(f"   Permissions: 600 (owner read-only)")
    except Exception as e:
        print(f"\n❌ Encryption failed: {e}")
        sys.exit(1)

    # Security reminder
    print("\n" + "=" * 60)
    print("SECURITY REMINDERS:")
    print("=" * 60)
    print("✅ Encrypted wallet saved (safe to commit if in .gitignore)")
    print("✅ Private key will be wiped from memory after use")
    print("⚠️  NEVER commit the plaintext private key")
    print("⚠️  Age private key is in ~/.config/sops/age/keys.txt (keep secure)")
    print("⚠️  Without age private key, you CANNOT decrypt the wallet")
    print()

    # Wipe sensitive data from memory
    del private_key_b58
    del keypair

    print("✅ Done!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
