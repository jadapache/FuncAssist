# OpenBao Agent: authenticates with AppRole and renders the FuncAssist keys into a
# memory-backed volume shared only with the backend container.
pid_file = "/tmp/bao-agent.pid"

vault {
  address = "http://openbao:8200"
}

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path                   = "/openbao/approle/role_id"
      secret_id_file_path                 = "/openbao/approle/secret_id"
      remove_secret_id_file_after_reading = false
    }
  }
}

template {
  contents    = "{{ with secret \"secret/data/funcassist\" }}{{ .Data.data.secret_key }}{{ end }}"
  destination = "/run/secrets/funcassist/secret_key"
  perms       = "0444"
}

template {
  contents    = "{{ with secret \"secret/data/funcassist\" }}{{ .Data.data.pbkdf2_salt }}{{ end }}"
  destination = "/run/secrets/funcassist/pbkdf2_salt"
  perms       = "0444"
}

template {
  contents    = "{{ with secret \"secret/data/funcassist\" }}{{ .Data.data.postgres_password }}{{ end }}"
  destination = "/run/secrets/funcassist/postgres_password"
  perms       = "0444"
}
