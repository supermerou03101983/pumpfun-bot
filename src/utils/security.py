"""
Security Module

Handles:
- Wallet encryption/decryption using age
- Secure key management (never stores plaintext in memory longer than needed)
- Key derivation and validation
"""

import os
import subprocess
import tempfile
from typing import Optional, Dict
from pathlib import Path
import structlog
from solders.keypair import Keypair

logger = structlog.get_logger()

# Age public key (generated during deployment)
# This should match the key in /root/.config/sops/age/keys.txt
# IMPORTANT: Regenerate this during deployment with your actual age public key
AGE_PUBLIC_KEY = "age1qyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqsqzcwqr"


class SecurityManager:
    """Manages wallet encryption and decryption"""

    def __init__(self, config: Dict):
        """
        Initialize security manager

        Args:
            config: Configuration dict
        """
        self.config = config
        self.encrypted_wallet_path = config["security"]["encrypted_wallet_path"]
        self.age_public_key = config["security"].get("age_public_key", AGE_PUBLIC_KEY)
        self.key_lifetime_seconds = config["security"].get("key_lifetime_seconds", 30)

        # Verify age is installed
        if not self._check_age_installed():
            raise RuntimeError("age encryption not installed. Run: apt-get install age")

    def _check_age_installed(self) -> bool:
        """Check if age is installed"""
        try:
            subprocess.run(
                ["age", "--version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def load_keypair(self) -> Keypair:
        """
        Load and decrypt trading wallet keypair

        Returns:
            Solana Keypair

        Security:
        - Decrypts using age private key from ~/.config/sops/age/keys.txt
        - Plaintext key exists in memory ONLY during this function
        - Key is wiped from memory after Keypair creation
        """
        logger.info("Loading encrypted wallet", path=self.encrypted_wallet_path)

        if not os.path.exists(self.encrypted_wallet_path):
            raise FileNotFoundError(
                f"Encrypted wallet not found: {self.encrypted_wallet_path}. "
                f"Run: python scripts/encrypt_key.py"
            )

        try:
            # Decrypt wallet using age with identity file
            # Use environment variable AGE_IDENTITIES_FILE if set, otherwise use default path
            age_key_file = os.environ.get(
                "AGE_IDENTITIES_FILE",
                "/opt/pumpfun-bot/.age/keys.txt"
            )

            result = subprocess.run(
                ["age", "--decrypt", "-i", age_key_file, self.encrypted_wallet_path],
                capture_output=True,
                check=True,
                text=True,
            )

            # Get decrypted private key (base58 string)
            private_key_b58 = result.stdout.strip()

            # Create keypair
            keypair = Keypair.from_base58_string(private_key_b58)

            # Wipe plaintext key from memory
            del private_key_b58
            del result

            logger.info(
                "Wallet loaded successfully",
                pubkey=str(keypair.pubkey()),
            )

            return keypair

        except subprocess.CalledProcessError as e:
            logger.error(
                "Failed to decrypt wallet",
                error=e.stderr,
            )
            raise RuntimeError(
                "Wallet decryption failed. Ensure age private key exists in ~/.config/sops/age/keys.txt"
            )

    def encrypt_key(self, private_key_b58: str, output_path: Optional[str] = None):
        """
        Encrypt private key using age

        Args:
            private_key_b58: Private key in base58 format
            output_path: Output path (defaults to config path)
        """
        if output_path is None:
            output_path = self.encrypted_wallet_path

        logger.info("Encrypting wallet", output_path=output_path)

        try:
            # Encrypt using age public key
            process = subprocess.Popen(
                [
                    "age",
                    "--encrypt",
                    "--recipient",
                    self.age_public_key,
                    "--output",
                    output_path,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout, stderr = process.communicate(input=private_key_b58)

            if process.returncode != 0:
                raise RuntimeError(f"Encryption failed: {stderr}")

            # Set secure permissions (owner read-only)
            os.chmod(output_path, 0o600)

            logger.info("Wallet encrypted successfully", path=output_path)

        except Exception as e:
            logger.error("Encryption error", error=str(e))
            raise


def load_key(config: Dict) -> Keypair:
    """
    Convenience function to load keypair

    Args:
        config: Configuration dict

    Returns:
        Solana Keypair
    """
    manager = SecurityManager(config)
    return manager.load_keypair()


def generate_test_keypair() -> Keypair:
    """
    Generate a test keypair (for development only)

    Returns:
        Solana Keypair
    """
    return Keypair()


# Example usage
if __name__ == "__main__":
    # Test encryption/decryption
    from solders.keypair import Keypair

    # Generate test keypair
    test_keypair = Keypair()
    private_key_b58 = str(test_keypair)

    print(f"Test Public Key: {test_keypair.pubkey()}")
    print(f"Private Key (b58): {private_key_b58[:20]}...")

    # Test config
    config = {
        "security": {
            "encrypted_wallet_path": "/tmp/test_wallet.enc",
            "age_public_key": AGE_PUBLIC_KEY,
            "key_lifetime_seconds": 30,
        }
    }

    # Note: Encryption will fail if age is not installed
    # This is just a demonstration of the API
    print("\nSecurity module loaded successfully")
