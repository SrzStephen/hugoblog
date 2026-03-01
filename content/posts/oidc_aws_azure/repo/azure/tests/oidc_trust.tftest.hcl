# Verifies that every federated identity credential created by this module is
# scoped to the SrzStephen GitHub organisation and restricted to the main branch.
#
# The oidc_subjects output is computed purely from var.github_repos, so it is
# fully known at plan time and these tests run without real Azure credentials.

mock_provider "azurerm" {
  mock_data "azurerm_subscription" {
    defaults = {
      id              = "/subscriptions/00000000-0000-0000-0000-000000000000"
      subscription_id = "00000000-0000-0000-0000-000000000000"
      tenant_id       = "11111111-1111-1111-1111-111111111111"
      display_name    = "Test Subscription"
    }
  }
}

mock_provider "azuread" {
  mock_data "azuread_client_config" {
    defaults = {
      client_id = "22222222-2222-2222-2222-222222222222"
      object_id = "33333333-3333-3333-3333-333333333333"
      tenant_id = "11111111-1111-1111-1111-111111111111"
    }
  }
}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000000"
  github_repos    = ["hugoblog", "another-repo"]
  app_name        = "test-github-deploy"
}

# Every federated credential subject must reference SrzStephen.
run "all_federated_subjects_scoped_to_srz_stephen" {
  command = plan

  assert {
    condition = alltrue([
      for repo, sub in output.oidc_subjects :
      startswith(sub, "repo:SrzStephen/")
    ])
    error_message = "One or more federated credential subjects reference an organisation other than SrzStephen: ${jsonencode(output.oidc_subjects)}"
  }

  # Belt-and-suspenders: confirm none slip through without the org prefix.
  assert {
    condition = !anytrue([
      for repo, sub in output.oidc_subjects :
      !startswith(sub, "repo:SrzStephen/")
    ])
    error_message = "Found subjects missing the 'repo:SrzStephen/' prefix: ${jsonencode(output.oidc_subjects)}"
  }

  # One credential per repo — no extras, no missing entries.
  assert {
    condition     = length(output.oidc_subjects) == length(var.github_repos)
    error_message = "Expected ${length(var.github_repos)} federated credentials but got ${length(output.oidc_subjects)}: ${jsonencode(output.oidc_subjects)}"
  }
}

# Azure federated credentials are intentionally restricted to the main branch
# only (unlike the AWS role which accepts any ref). Confirm that invariant holds.
run "federated_subjects_restricted_to_main_branch" {
  command = plan

  assert {
    condition = alltrue([
      for repo, sub in output.oidc_subjects :
      endswith(sub, ":ref:refs/heads/main")
    ])
    error_message = "All federated credential subjects must be scoped to the main branch — got: ${jsonencode(output.oidc_subjects)}"
  }
}
