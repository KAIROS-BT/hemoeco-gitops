terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Configurado en CI con -backend-config (ver workflow deploy.yml).
  # Auth al state por OIDC + Azure AD (la identidad federada tiene
  # "Storage Blob Data Contributor" sobre el storage account; no usa access key).
  backend "azurerm" {
    use_oidc         = true
    use_azuread_auth = true
  }
}

provider "azurerm" {
  features {}
  use_oidc = true
}
