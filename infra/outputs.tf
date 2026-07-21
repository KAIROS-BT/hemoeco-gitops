output "storage_account_name" {
  value = azurerm_storage_account.demo.name
}

output "resource_group" {
  value = azurerm_storage_account.demo.resource_group_name
}

output "location" {
  value = azurerm_storage_account.demo.location
}

output "resource_id" {
  value = azurerm_storage_account.demo.id
}

output "applied_tags" {
  value = azurerm_storage_account.demo.tags
}
