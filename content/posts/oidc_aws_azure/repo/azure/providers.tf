terraform {
  required_version = ">= 1.14"

  cloud {
    hostname     = "app.terraform.io"
    organization = "stephenorg"

    workspaces {
      # Workspace is auto-created on first `terraform init` if it does not exist.
      project = "oidc_base"
      name    = "github-oidc-azure"
    }
  }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

provider "azuread" {}
