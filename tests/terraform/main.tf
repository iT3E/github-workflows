# Fixture for actions/terraform in self-test.yaml: no providers to download
# and local state, so a plan always shows one resource to add.
terraform {
  required_version = ">= 1.6"
}

variable "greeting" {
  type    = string
  default = "hello"
}

resource "terraform_data" "example" {
  input = var.greeting
}
