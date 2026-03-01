variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "app_name" {
  description = "Display name for the Azure AD App Registration"
  type        = string
  default     = "github-deploy"
}

variable "additional_owners" {
  description = "Extra Azure AD object IDs to add as owners of the App Registration and Service Principal"
  type        = list(string)
  default     = []
}

variable "github_org" {
  description = "GitHub organisation name used as the OIDC subject prefix"
  type        = string
  default     = "SrzStephen"
}

variable "github_repos" {
  description = "GitHub repository names (within the github_org) to grant federated access. All refs are permitted."
  type        = list(string)
  default     = ["hugoblog"]
}

variable "role_assignments" {
  description = "List of Azure RBAC role definition names to assign to the service principal at the subscription scope"
  type        = list(string)
  default     = []
  # Example: ["Contributor", "Reader"]
}
