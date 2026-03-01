data "azurerm_subscription" "current" {}

# Resolve the identity running Terraform so it can be set as app owner
data "azuread_client_config" "current" {}

# Azure AD App Registration
resource "azuread_application" "github_deploy" {
  display_name     = var.app_name
  sign_in_audience = "AzureADMyOrg" # single-tenant — correct for deploy identities

  # Keep the Terraform caller as an owner so the registration isn't orphaned
  owners = concat(
    [data.azuread_client_config.current.object_id],
    var.additional_owners,
  )
}

# Service Principal backed by the App Registration
resource "azuread_service_principal" "github_deploy" {
  client_id    = azuread_application.github_deploy.client_id
  use_existing = false

  owners = concat(
    [data.azuread_client_config.current.object_id],
    var.additional_owners,
  )
}

# Federated Identity Credential — one per repository, main branch only
resource "azuread_application_federated_identity_credential" "github" {
  for_each = toset(var.github_repos)

  application_id = azuread_application.github_deploy.id
  display_name   = each.value

  audiences = ["api://AzureADTokenExchange"]
  issuer    = "https://token.actions.githubusercontent.com"
  subject   = "repo:${var.github_org}/${each.value}:ref:refs/heads/main"
}

# Assign Azure RBAC role to the service principal at the subscription scope
resource "azurerm_role_assignment" "github_deploy" {
  for_each = toset(var.role_assignments)

  scope                = data.azurerm_subscription.current.id
  role_definition_name = each.value
  principal_id         = azuread_service_principal.github_deploy.object_id
}
