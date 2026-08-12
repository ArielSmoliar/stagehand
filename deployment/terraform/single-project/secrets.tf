# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

locals {
  grafana_secret_ids = toset([
    "stagehand-grafana-read-token",
    "stagehand-grafana-otlp-token",
  ])
}

# Terraform manages only the secret containers. Secret versions are added
# interactively so credential values never enter source control or state.
resource "google_secret_manager_secret" "grafana" {
  for_each  = local.grafana_secret_ids
  project   = var.project_id
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [resource.google_project_service.services]
}

# Admin token secret container for supervisor console verification
resource "google_secret_manager_secret" "admin_token" {
  project   = var.project_id
  secret_id = "stagehand-admin-token"

  replication {
    auto {}
  }

  depends_on = [resource.google_project_service.services]
}

# Scope Secret Manager Accessor roles specifically to individual secrets
resource "google_secret_manager_secret_iam_member" "grafana_read_accessor" {
  project    = var.project_id
  secret_id  = "stagehand-grafana-read-token"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.app_sa.email}"
  depends_on = [google_secret_manager_secret.grafana]
}

resource "google_secret_manager_secret_iam_member" "grafana_otlp_accessor" {
  project    = var.project_id
  secret_id  = "stagehand-grafana-otlp-token"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.app_sa.email}"
  depends_on = [google_secret_manager_secret.grafana]
}

resource "google_secret_manager_secret_iam_member" "admin_token_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.admin_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_sa.email}"
}
