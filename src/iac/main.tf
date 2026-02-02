# Terraform configuration for RPS Game VM infrastructure

terraform {
  required_version = ">= 1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

variable "resource_group_name" {
  description = "Name of the Azure resource group"
  type        = string
  default     = "rps-game-rg"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "westeurope"
}

variable "vm_size" {
  description = "Size of the VM"
  type        = string
  default     = "Standard_B1s"
}

variable "admin_username" {
  description = "Admin username for the VM"
  type        = string
  default     = "azureuser"
}

variable "trust_domain" {
  description = "SPIFFE trust domain for this deployment"
  type        = string
  default     = "noah.inter-cloud-thi.de"
}

# Resource Group
resource "azurerm_resource_group" "rps" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    environment = "demo"
    project     = "rock-paper-scissors"
  }
}

# Virtual Network with proper segmentation
resource "azurerm_virtual_network" "rps" {
  name                = "rps-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.rps.location
  resource_group_name = azurerm_resource_group.rps.name
}

# Subnet for game servers
resource "azurerm_subnet" "game" {
  name                 = "game-subnet"
  resource_group_name  = azurerm_resource_group.rps.name
  virtual_network_name = azurerm_virtual_network.rps.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Network Security Group - restrictive by default
resource "azurerm_network_security_group" "rps" {
  name                = "rps-nsg"
  location            = azurerm_resource_group.rps.location
  resource_group_name = azurerm_resource_group.rps.name

  # Allow SPIFFE mTLS game traffic
  security_rule {
    name                       = "AllowGameTraffic"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "9002"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
    description                = "Allow RPS game traffic on mTLS port"
  }

  # Allow SSH from specific IPs only (not 0.0.0.0/0)
  security_rule {
    name                       = "AllowSSH"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "10.0.0.0/8"  # Internal only
    destination_address_prefix = "*"
    description                = "Allow SSH from internal network only"
  }

  # Deny all other inbound
  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
    description                = "Deny all other inbound traffic"
  }
}

# Associate NSG with subnet
resource "azurerm_subnet_network_security_group_association" "game" {
  subnet_id                 = azurerm_subnet.game.id
  network_security_group_id = azurerm_network_security_group.rps.id
}

# Public IP for game server
resource "azurerm_public_ip" "rps" {
  name                = "rps-pip"
  location            = azurerm_resource_group.rps.location
  resource_group_name = azurerm_resource_group.rps.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

# Network Interface
resource "azurerm_network_interface" "rps" {
  name                = "rps-nic"
  location            = azurerm_resource_group.rps.location
  resource_group_name = azurerm_resource_group.rps.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.game.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.rps.id
  }
}

# Linux VM for game server
resource "azurerm_linux_virtual_machine" "rps" {
  name                = "rps-game-vm"
  resource_group_name = azurerm_resource_group.rps.name
  location            = azurerm_resource_group.rps.location
  size                = var.vm_size
  admin_username      = var.admin_username

  network_interface_ids = [
    azurerm_network_interface.rps.id,
  ]

  # Use SSH key authentication (no password)
  admin_ssh_key {
    username   = var.admin_username
    public_key = file("~/.ssh/id_rsa.pub")
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    
    # Enable encryption at rest
    disk_encryption_set_id = null  # Use platform-managed keys
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  # Security best practices
  disable_password_authentication = true
  encryption_at_host_enabled      = false  # Requires specific VM size
  secure_boot_enabled             = true
  vtpm_enabled                    = true

  custom_data = base64encode(<<-EOF
    #!/bin/bash
    # Install Docker
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker ${var.admin_username}
    
    # Install SPIRE
    cd /opt
    wget https://github.com/spiffe/spire/releases/download/v1.13.3/spire-1.13.3-linux-amd64-musl.tar.gz
    tar -xzf spire-1.13.3-linux-amd64-musl.tar.gz
    
    # Pull game image
    docker pull ghcr.io/npaulat99/rock-paper-scissors:latest
    
    echo "Trust domain: ${var.trust_domain}" > /etc/rps-config
  EOF
  )

  tags = {
    environment  = "demo"
    project      = "rock-paper-scissors"
    trust_domain = var.trust_domain
  }
}

# Output values
output "public_ip" {
  value       = azurerm_public_ip.rps.ip_address
  description = "Public IP address of the game server"
}

output "game_endpoint" {
  value       = "https://${azurerm_public_ip.rps.ip_address}:9002"
  description = "HTTPS endpoint for the game server"
}

output "spiffe_id" {
  value       = "spiffe://${var.trust_domain}/game-server"
  description = "SPIFFE ID for this game server"
}
