output "role_arn" {
  description = "ARN of the GitHub deploy IAM role"
  value       = aws_iam_role.github_deploy.arn
}

output "role_name" {
  description = "Name of the GitHub deploy IAM role"
  value       = aws_iam_role.github_deploy.name
}

output "oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider"
  value       = aws_iam_openid_connect_provider.github.arn
}

output "assume_role_policy_json" {
  description = "JSON of the assume-role policy document"
  value       = data.aws_iam_policy_document.github_assume_role.json
}
