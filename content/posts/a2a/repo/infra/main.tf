terraform {
  required_version = ">= 1.5"

  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "azuread" {}

data "azuread_client_config" "current" {}

# ---------------------------------------------------------------------------
# App Registration
# ---------------------------------------------------------------------------
resource "azuread_application" "a2a_server" {
  display_name = var.app_display_name

  sign_in_audience = "AzureADMyOrg"

  api {
    requested_access_token_version = 2
  }

  web {
    redirect_uris = var.redirect_uris

    implicit_grant {
      id_token_issuance_enabled = true
    }
  }

  app_role {
    allowed_member_types = ["User"]
    display_name         = "Agent Caller"
    value                = "agent.caller"
    description          = "Can invoke restricted A2A agents (e.g. DuckDuckGo)."
    enabled              = true
    id                   = random_uuid.agent_caller_role_id.result
  }

  app_role {
    allowed_member_types = ["User"]
    display_name         = "Data Fetch Admin Caller"
    value                = "data_fetch_admin.caller"
    description          = "Can invoke data fetch admin operations."
    enabled              = true
    id                   = random_uuid.data_fetch_admin_caller_role_id.result
  }

  owners = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal" "a2a_server" {
  client_id = azuread_application.a2a_server.client_id
  owners    = [data.azuread_client_config.current.object_id]
}

# ---------------------------------------------------------------------------
# Client Secret
# ---------------------------------------------------------------------------
resource "azuread_application_password" "a2a_server" {
  application_id = azuread_application.a2a_server.id
  display_name   = "a2a-server-secret"
}

# ---------------------------------------------------------------------------
# Stable UUID for the app role
# ---------------------------------------------------------------------------
resource "random_uuid" "agent_caller_role_id" {}
resource "random_uuid" "data_fetch_admin_caller_role_id" {}

# ---------------------------------------------------------------------------
# Assign users to the Agent Caller role
# ---------------------------------------------------------------------------
data "azuread_user" "agent_callers" {
  for_each            = toset(var.agent_caller_upns)
  user_principal_name = each.value
}

resource "azuread_app_role_assignment" "agent_callers" {
  for_each            = data.azuread_user.agent_callers
  app_role_id         = random_uuid.agent_caller_role_id.result
  principal_object_id = each.value.object_id
  resource_object_id  = azuread_service_principal.a2a_server.object_id
}

# ---------------------------------------------------------------------------
# Assign users to the Data Fetch Admin Caller role
# ---------------------------------------------------------------------------
data "azuread_user" "data_fetch_admin_callers" {
  for_each            = toset(var.data_fetch_admin_caller_upns)
  user_principal_name = each.value
}

resource "azuread_app_role_assignment" "data_fetch_admin_callers" {
  for_each            = data.azuread_user.data_fetch_admin_callers
  app_role_id         = random_uuid.data_fetch_admin_caller_role_id.result
  principal_object_id = each.value.object_id
  resource_object_id  = azuread_service_principal.a2a_server.object_id
}
