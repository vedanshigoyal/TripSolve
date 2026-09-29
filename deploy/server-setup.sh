#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 EC2 instance. Run as the default `ubuntu` user.
set -euo pipefail

# Docker Engine + Compose plugin (official convenience script).
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

# 2 GB swap: t3.small has 2 GB RAM, and building Next.js + running PostGIS needs headroom.
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# Security updates install automatically.
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y unattended-upgrades

mkdir -p ~/tripsolve
echo "Server ready. Log out and back in once so the docker group applies."
