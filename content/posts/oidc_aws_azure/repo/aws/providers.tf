terraform {
  required_version = ">= 1.14"

  cloud {
    hostname     = "app.terraform.io"
    organization = "stephenorg"

    workspaces {
      # Workspace is auto-created on first `terraform init` if it does not exist.
      project = "oidc_base"
      name    = "github-oidc-aws"
    }
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region[0]

  default_tags {
    tags = {
      ManagedBy = "Terraform"
      StackName = "GitlabOIDC"
    }
  }
}
