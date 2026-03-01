output "client_id" {
  description = "Azure AD Application (client) ID — set as AZURE_CLIENT_ID in GitHub secrets"
  value       = azuread_application.github_deploy.client_id
}

output "tenant_id" {
  description = "Azure tenant ID — set as AZURE_TENANT_ID in GitHub secrets"
  value       = data.azurerm_subscription.current.tenant_id
}

output "subscription_id" {
  description = "Azure subscription ID — set as AZURE_SUBSCRIPTION_ID in GitHub secrets"
  value       = data.azurerm_subscription.current.subscription_id
}

output "service_principal_object_id" {
  description = "Object ID of the service principal"
  value       = azuread_service_principal.github_deploy.object_id
}

output "oidc_subjects" {
  description = "OIDC token subjects configured for each federated identity credential, keyed by repository name"
  value       = { for repo, cred in azuread_application_federated_identity_credential.github : repo => cred.subject }
}
