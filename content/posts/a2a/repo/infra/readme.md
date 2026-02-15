# A2A Server — Azure AD Infrastructure
Minimal description of the terraform infrastructure set up for this.
## Key points
* Use an application **role** instead of assigning an AD group to avoid having to pull through all user groups
* Two roles
  * `agent.caller` allows access to restricted tool (DuckDuckGo)
  * `data_fetch_admin.caller` allows access to rows in `data_fetch` (row level access control example)
* Add an arbitrary list of users to the roles via their user principal names

## Usage
```zsh
terraform plan
terraform apply
terraform output -raw azure_client_secret
```
And populate environment variables in [.env](../.env)

## Architecture

```mermaid
graph TD
    subgraph Terraform
        TF[Terraform Config<br/>v1.5+]
    end

    subgraph Azure AD
        APP[App Registration<br/>&quot;A2A Server&quot;]
        SP[Service Principal]
        SECRET[Client Secret<br/>&quot;a2a-server-secret&quot;]

        subgraph App Roles
            ROLE_AC[agent.caller<br/>Agent Caller]
            ROLE_DFA[data_fetch_admin.caller<br/>Data Fetch Admin Caller]
        end
    end

    subgraph Users
        U_AC[Agent Caller Users]
        U_DFA[Data Fetch Admin Users]
    end

    subgraph A2A Application
        CLIENT[Streamlit Client<br/>localhost:8501]
        SERVER[A2A Server]
    end

    TF -->|creates| APP
    APP -->|registers| SP
    APP -->|generates| SECRET
    APP -->|defines| ROLE_AC
    APP -->|defines| ROLE_DFA

    U_AC -->|assigned to| ROLE_AC
    U_DFA -->|assigned to| ROLE_DFA

    ROLE_AC -->|authorizes| SERVER
    ROLE_DFA -->|authorizes| SERVER

    CLIENT -->|redirect_uri| APP
    SECRET -->|AZURE_CLIENT_SECRET| SERVER
    APP -->|AZURE_CLIENT_ID| SERVER
```

## Resource Summary

| Resource | Type | Purpose |
|---|---|---|
| `azuread_application.a2a_server` | App Registration | OAuth2 identity for the A2A server (sign-in audience: single tenant) |
| `azuread_service_principal.a2a_server` | Service Principal | Enterprise app backing the registration |
| `azuread_application_password.a2a_server` | Client Secret | Server-side credential for token validation |
| `azuread_app_role_assignment.agent_callers` | Role Assignment | Grants `agent.caller` role to specified users |
| `azuread_app_role_assignment.data_fetch_admin_callers` | Role Assignment | Grants `data_fetch_admin.caller` role to specified users |