# OpenBao server. Internal Docker network only: the port is not published.
storage "raft" {
  path    = "/openbao/file"
  node_id = "funcassist-bao-1"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

api_addr      = "http://openbao:8200"
cluster_addr  = "http://openbao:8201"
ui            = false
