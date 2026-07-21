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

  # El SP tiene Contributor solo sobre el RG objetivo (minimo privilegio) y no
  # puede registrar resource providers a nivel suscripcion (requiere .../register/action).
  # Desactivamos el auto-registro; Microsoft.Storage ya esta registrado en la suscripcion.
  # Si agregas recursos de otro RP, registralo antes como Owner: az provider register --namespace <RP>.
  resource_provider_registrations = "none"
}
