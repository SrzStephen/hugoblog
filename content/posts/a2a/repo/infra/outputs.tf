output "azure_client_id" {
  description = "Application (client) ID — set as AZURE_CLIENT_ID."
  value       = azuread_application.a2a_server.client_id
}

output "azure_tenant_id" {
  description = "Tenant ID — set as AZURE_TENANT_ID."
  value       = data.azuread_client_config.current.tenant_id
}

output "azure_client_secret" {
  description = "Client secret — set as AZURE_CLIENT_SECRET."
  value       = azuread_application_password.a2a_server.value
  sensitive   = true
}