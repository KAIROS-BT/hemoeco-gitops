terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Configurado en CI con -backend-config (ver workflow deploy.yml)
  backend "azurerm" {}
}

provider "azurerm" {
  features {}
  use_oidc = true
}
