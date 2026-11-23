import base64
import json


from app.core.secrets import SECRET_PREFIX, decrypt_bytes, decrypt_secret, encrypt_secret


def test_secrets_use_aes_256_gcm_and_detect_tampering():
  token = encrypt_secret("sk-test-123")
  assert token.startswith(SECRET_PREFIX)
  assert decrypt_secret(token) == "sk-test-123"
  raw = bytearray(base64.urlsafe_b64decode(token[len(SECRET_PREFIX):]))
  raw[-1] ^= 1
  tampered = SECRET_PREFIX + base64.urlsafe_b64encode(bytes(raw)).decode()
  assert decrypt_secret(tampered) == ""


def test_migration_reencrypts_legacy_fernet_values():
  from scripts import migrate_fernet_to_gcm as mig

  prefixed = "enc::" + mig.PREFIXED.encrypt(b"groq-key").decode()
  raw = mig.RAW.encrypt(json.dumps({"client_secret": "abc"}).encode()).decode()
  doc = json.dumps({"ai": {"groq_api_key": prefixed}})

  new_prefixed, n1 = mig._convert(prefixed)
  new_raw, n2 = mig._convert(raw)
  new_doc, n3 = mig._convert(doc)

  assert (n1, n2, n3) == (1, 1, 1)
  assert decrypt_bytes(new_prefixed) == b"groq-key"
  assert json.loads(decrypt_bytes(new_raw)) == {"client_secret": "abc"}
  assert decrypt_secret(json.loads(new_doc)["ai"]["groq_api_key"]) == "groq-key"
  assert mig._convert("texto normal") == ("texto normal", 0)
