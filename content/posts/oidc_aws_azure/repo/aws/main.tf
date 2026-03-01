data "aws_caller_identity" "current" {}

# GitHub OIDC Provider
# Note: As of Oct 2023 AWS IAM validates GitHub's OIDC tokens via the JWKS endpoint
# directly, so thumbprints are no longer enforced for this provider. They are kept
# here because the resource attribute is required — AWS ignores the values.
resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = ["sts.amazonaws.com"]

  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

# IAM Role for GitHub Actions
resource "aws_iam_role" "github_deploy" {
  name = var.role_name

  assume_role_policy = data.aws_iam_policy_document.github_assume_role.json

  tags = var.tags
}

data "aws_iam_policy_document" "github_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for repo in var.github_repos : "repo:${var.github_org}/${repo}:ref:refs/heads/main"]
    }
  }
}

# Attach managed policies to the role
resource "aws_iam_role_policy_attachment" "github_deploy" {
  for_each = toset(var.managed_policy_arns)

  role       = aws_iam_role.github_deploy.name
  policy_arn = each.value
}

# Attach every policy file in the policies/ directory as a separate inline policy
resource "aws_iam_role_policy" "github_deploy_policies" {
  for_each = { for f in fileset("${path.module}/policies", "*.json") : trimsuffix(f, ".json") => f }

  name   = "${var.role_name}-${each.key}"
  role   = aws_iam_role.github_deploy.id
  policy = templatefile("${path.module}/policies/${each.value}", {
    account_id = data.aws_caller_identity.current.account_id
  })
}
