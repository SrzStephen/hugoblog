variable "app_display_name" {
  description = "Display name for the Azure AD app registration."
  type        = string
  default     = "A2A Server"
}

variable "redirect_uris" {
  description = "OAuth2 redirect URIs for the app registration."
  type        = list(string)
  default     = ["http://localhost:8501/"]
}

variable "agent_caller_upns" {
  description = "User principal names to assign the Agent Caller app role."
  type        = list(string)
  default     = ["stephen@REDACT.onmicrosoft.com","REDACT.com#EXT#@REDACT.onmicrosoft.com"]
}

variable "data_fetch_admin_caller_upns" {
  description = "User principal names to assign the Data Fetch Admin Caller app role."
  type        = list(string)
  default     = ["stephen@REDACT.onmicrosoft.com","REDACT.com#EXT#@REDACT.onmicrosoft.com"]
}

