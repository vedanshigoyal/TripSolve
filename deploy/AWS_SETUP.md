# Deploying TripSolve on AWS (Free plan)

One EC2 server runs everything in Docker: PostGIS, FastAPI, Next.js, and Caddy (HTTPS).
Cost is about $21/month (t3.small, 20 GB of disk, Elastic IP). Your Free-plan credits pay for it, and the Free plan can't bill you.

## 1. Safety first: budget alert (2 min)

Billing and Cost Management → **Budgets** → Create budget → *Use a template* → **Zero spend budget**, with your email.
This also counts toward the $100 bonus credits.

## 2. Pick the region

Top-right region menu → **Asia Pacific (Mumbai) ap-south-1**. It is the closest to Jaipur. Create everything below in this region.

## 3. Key pair (1 min)

EC2 → **Key pairs** → Create key pair
* Name: `tripsolve-key`, type **RSA**, format **.pem**
* The file downloads once. Move it to `C:\Users\BIT\.ssh\tripsolve-key.pem` and never commit or share it.

## 4. Launch the server (5 min)

EC2 → **Launch instance**
| Setting | Value |
|---|---|
| Name | `tripsolve` |
| AMI | **Ubuntu Server 24.04 LTS** (x86, "Free tier eligible") |
| Instance type | **t3.small** ("Free tier eligible") |
| Key pair | `tripsolve-key` |
| Network → Firewall | *Create security group* with 3 rules: **SSH (22) from My IP**, **HTTP (80) from Anywhere**, **HTTPS (443) from Anywhere** |
| Storage | **20 GiB gp3** |

Click **Launch instance**.

## 5. Fixed public IP (2 min)

EC2 → **Elastic IPs** → Allocate → then *Actions → Associate* → choose the `tripsolve` instance.
Note the IP (for example `13.233.10.5`). The site will be at `https://13-233-10-5.sslip.io`.

## 6. Send Claude the IP and the key path

From here Claude runs the rest:
```bash
ssh -i ~/.ssh/tripsolve-key.pem ubuntu@<IP> 'bash -s' < deploy/server-setup.sh   # once
bash deploy/deploy.sh <IP> ~/.ssh/tripsolve-key.pem                               # every update
```

## Everyday use

* **Update the site:** commit, then `bash deploy/deploy.sh <IP> <key>`.
* **Logs:** `ssh -i <key> ubuntu@<IP> "cd tripsolve && docker compose -f docker-compose.prod.yml logs -f backend"`.
* **Save credits when not demoing:** *Stop* the instance (not *Terminate*). Compute charges stop, but the disk (~$1.8) and the Elastic IP (~$3.6) are still charged. Data survives.
* **Your SSH IP changed** (home vs college Wi-Fi)? Edit the security group's SSH rule → "My IP".
* **When you are done (before March 2027):** Terminate the instance, **release the Elastic IP**, and delete leftover volumes and snapshots.
