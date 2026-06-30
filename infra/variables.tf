variable "resource_group_name" {
  type        = string
  description = "Grupo de recursos donde se despliega."
}

variable "location" {
  type    = string
  default = "westus"
}

variable "storage_name" {
  type        = string
  description = "Nombre de la cuenta de almacenamiento de ejemplo."
}

variable "common_tags" {
  type        = map(string)
  description = "Etiquetas de gobernanza aplicadas a todos los recursos."

  validation {
    condition     = alltrue([for k in ["workload", "ambiente", "owner"] : contains(keys(var.common_tags), k)])
    error_message = "Faltan etiquetas requeridas: workload, ambiente, owner."
  }

  validation {
    condition     = contains(["prod", "dev", "test"], try(var.common_tags["ambiente"], ""))
    error_message = "La etiqueta 'ambiente' debe ser prod, dev o test."
  }
}
