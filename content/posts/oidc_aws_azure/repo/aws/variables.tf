variable "role_name" {
  description = "Name of the IAM role for GitHub Actions to assume"
  type        = string
  default     = "github-deploy-role"
}

variable "github_org" {
  description = "GitHub organisation name prepended to each repository in the OIDC sub condition"
  type        = string
  default     = "SrzStephen"
}

variable "github_repos" {
  description = "List of GitHub repository names (without org prefix) allowed to assume the role"
  type        = list(string)
  default     = ["hugoblog"]

  validation {
    condition     = length(var.github_repos) > 0
    error_message = "At least one repository must be specified."
  }
}

variable "managed_policy_arns" {
  description = "List of managed IAM policy ARNs to attach to the role"
  type        = list(string)
  default     = []
}

variable "aws_region" {
  description = "AWS regions to deploy into"
  type        = list(string)
  default     = ["us-east-1"]
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
